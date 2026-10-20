from decimal import Decimal

from django.conf import settings
from django.utils import timezone
from PIL import Image, UnidentifiedImageError
from rest_framework import serializers

from core.archivos import huella_archivo
from finanzas.api.serializers import DelHogarMixin
from finanzas.models import Categoria, Cuenta, Movimiento
from tickets.models import LineaTicket, Ticket

# Firmas ("magic bytes"): el tipo real lo dice el contenido, no la extensión ni el Content-Type del cliente
FIRMAS = {
    b"%PDF-": "application/pdf",
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
}


def detectar_tipo(archivo) -> str | None:
    cabecera = archivo.read(16)
    archivo.seek(0)
    if cabecera[:4] == b"RIFF" and cabecera[8:12] == b"WEBP":
        return "image/webp"
    return next((tipo for firma, tipo in FIRMAS.items() if cabecera.startswith(firma)), None)


class SubirTicketSerializer(DelHogarMixin, serializers.Serializer):
    campos_del_hogar = {"cuenta": Cuenta}
    archivo = serializers.FileField()
    cuenta = serializers.PrimaryKeyRelatedField(queryset=Cuenta.objects.none())

    def validate_archivo(self, archivo):
        if archivo.size > settings.TICKETS_TAMANO_MAXIMO:
            raise serializers.ValidationError("El archivo no puede superar los 10 MB.")
        tipo = detectar_tipo(archivo)
        if tipo is None:
            raise serializers.ValidationError("Sube una foto (JPEG, PNG o WebP) o un PDF.")
        if tipo.startswith("image/"):
            try:
                with Image.open(archivo) as imagen:
                    imagen.verify()  # detecta imágenes truncadas o corruptas sin decodificarlas enteras
            except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as e:
                raise serializers.ValidationError("La imagen está dañada.") from e
            finally:
                archivo.seek(0)
        self.context["tipo"] = tipo
        return archivo

    def validate(self, datos):
        datos["tipo"] = self.context.pop("tipo")
        datos["huella_archivo"] = huella_archivo(datos["archivo"])
        repetido = Ticket.objects.filter(hogar=self.context["hogar"], huella_archivo=datos["huella_archivo"]).first()
        if repetido:
            raise serializers.ValidationError({"archivo": f"Este ticket ya se subió (ticket {repetido.pk})."})
        return datos


class LineaTicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = LineaTicket
        fields = ["orden", "descripcion", "cantidad", "precio_unitario", "importe"]


class MovimientoDeTicketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Movimiento
        fields = ["id", "fecha", "importe", "concepto", "categoria", "revisado"]


class TicketSerializer(serializers.ModelSerializer):
    lineas = LineaTicketSerializer(many=True, read_only=True)
    movimiento = MovimientoDeTicketSerializer(read_only=True)

    class Meta:
        model = Ticket
        fields = [
            "id",
            "estado",
            "cuenta",
            "nombre_original",
            "tipo",
            "confianza",
            "error",
            "datos_ia",
            "intentos",
            "lineas",
            "movimiento",
            "creado",
            "procesado_en",
        ]
        read_only_fields = fields


class ConfirmarTicketSerializer(DelHogarMixin, serializers.Serializer):
    campos_del_hogar = {"categoria": Categoria}
    fecha = serializers.DateField()
    total = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal("0.01"))
    concepto = serializers.CharField(max_length=255)
    categoria = serializers.PrimaryKeyRelatedField(queryset=Categoria.objects.none(), allow_null=True, required=False)

    def validate_fecha(self, valor):
        if valor > timezone.localdate():
            raise serializers.ValidationError("La fecha no puede ser futura.")
        return valor


class ReprocesarTicketSerializer(serializers.Serializer):
    repetir_ocr = serializers.BooleanField(default=False)


class UrlArchivoSerializer(serializers.Serializer):
    url = serializers.URLField()

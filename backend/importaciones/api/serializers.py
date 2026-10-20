from django.conf import settings
from rest_framework import serializers

from core.archivos import huella_archivo
from finanzas.api.serializers import DelHogarMixin
from finanzas.models import Cuenta
from importaciones.models import FilaImportacion, Importacion


class SubirImportacionSerializer(DelHogarMixin, serializers.Serializer):
    campos_del_hogar = {"cuenta": Cuenta}
    archivo = serializers.FileField()
    cuenta = serializers.PrimaryKeyRelatedField(queryset=Cuenta.objects.none())

    def validate_archivo(self, archivo):
        if archivo.size > settings.IMPORTACION_TAMANO_MAXIMO:
            raise serializers.ValidationError("El archivo no puede superar los 5 MB.")
        cabecera = archivo.read(2048)
        archivo.seek(0)
        if cabecera.startswith(b"%PDF-"):
            self.context["formato"] = Importacion.Formato.PDF
        elif b"\x00" in cabecera:  # un CSV es texto: un byte nulo delata un binario (xlsx, imagen…)
            raise serializers.ValidationError("Sube el extracto en CSV o PDF.")
        else:
            self.context["formato"] = Importacion.Formato.CSV
        return archivo

    def validate(self, datos):
        datos["formato"] = self.context.pop("formato")
        datos["huella_archivo"] = huella_archivo(datos["archivo"])
        repetida = (
            Importacion.objects.filter(hogar=self.context["hogar"], huella_archivo=datos["huella_archivo"])
            .exclude(estado__in=[Importacion.Estado.DESHECHA, Importacion.Estado.ERROR])
            .first()
        )
        if repetida:
            raise serializers.ValidationError({"archivo": f"Este extracto ya se importó (importación {repetida.pk})."})
        return datos


class ImportacionSerializer(serializers.ModelSerializer):
    progreso = serializers.IntegerField(read_only=True)

    class Meta:
        model = Importacion
        fields = [
            "id",
            "estado",
            "cuenta",
            "nombre_original",
            "formato",
            "total_filas",
            "procesadas",
            "progreso",
            "creados",
            "conciliados",
            "duplicados",
            "resumen",
            "avisos",
            "error",
            "creado",
            "terminado_en",
        ]
        read_only_fields = fields


class FilaImportacionSerializer(serializers.ModelSerializer):
    coincide_con_concepto = serializers.CharField(source="coincide_con.concepto", read_only=True, default=None)

    class Meta:
        model = FilaImportacion
        fields = [
            "id",
            "numero",
            "fecha",
            "concepto",
            "importe",
            "accion",
            "coincide_con",
            "coincide_con_concepto",
            "movimiento",
        ]
        read_only_fields = fields


class ConfirmarImportacionSerializer(serializers.Serializer):
    separar = serializers.ListField(child=serializers.IntegerField(), required=False, default=list, max_length=5000)

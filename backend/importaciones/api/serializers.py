import re
from datetime import date, datetime

from django.conf import settings
from rest_framework import serializers

from core.archivos import huella_archivo
from finanzas.api.serializers import DelHogarMixin
from finanzas.models import Categoria, Cuenta
from importaciones.models import FilaImportacion, Importacion, PerfilBanco

CAMPOS_PERFIL = {"fecha", "concepto", "importe", "cargo", "abono", "saldo"}


class PerfilBancoSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerfilBanco
        fields = ["id", "nombre", "separador", "filas_a_saltar", "columnas", "formato_fecha"]

    def validate_columnas(self, columnas):
        if not isinstance(columnas, dict) or not columnas:
            raise serializers.ValidationError('Un objeto como {"fecha": 0, "concepto": 2, "importe": 3}.')
        if desconocidas := set(columnas) - CAMPOS_PERFIL:
            raise serializers.ValidationError(f"Campos desconocidos: {', '.join(sorted(desconocidas))}.")
        if any(type(v) is not int or not 0 <= v < 100 for v in columnas.values()):  # bool es int: type() lo excluye
            raise serializers.ValidationError("Cada posición es un número entero desde 0.")
        if not {"fecha", "concepto"} <= columnas.keys():
            raise serializers.ValidationError("Faltan las columnas de fecha y concepto.")
        if "importe" not in columnas and not {"cargo", "abono"} <= columnas.keys():
            raise serializers.ValidationError("Indica la columna de importe, o las de cargo y abono.")
        if len(set(columnas.values())) != len(columnas):
            raise serializers.ValidationError("Dos campos no pueden estar en la misma columna.")
        return columnas

    def validate_formato_fecha(self, formato):
        # Ida y vuelta con una fecha que lo distingue todo (día 31 > 12): "%d" sin "%m" o "%m/%d" no pasan
        if "%Y" not in formato and "%y" not in formato:
            raise serializers.ValidationError("Falta el año (%Y o %y).")
        prueba = date(2026, 1, 31)
        try:
            ok = datetime.strptime(prueba.strftime(formato), formato).date() == prueba
        except (ValueError, re.error):  # "%d/%d/%Y": directiva repetida
            ok = False
        if not ok:
            raise serializers.ValidationError("Formato no válido. Ejemplos: %d/%m/%Y, %Y-%m-%d, %d.%m.%y")
        return formato


class SubirImportacionSerializer(DelHogarMixin, serializers.Serializer):
    campos_del_hogar = {"cuenta": Cuenta, "perfil": PerfilBanco}
    archivo = serializers.FileField()
    cuenta = serializers.PrimaryKeyRelatedField(queryset=Cuenta.objects.none())
    perfil = serializers.PrimaryKeyRelatedField(queryset=PerfilBanco.objects.none(), required=False, allow_null=True)

    def validate_archivo(self, archivo):
        if archivo.size > settings.IMPORTACION_TAMANO_MAXIMO:
            raise serializers.ValidationError("El archivo no puede superar los 5 MB.")
        cabecera = archivo.read(2048)
        archivo.seek(0)
        if cabecera.startswith(b"%PDF-"):
            self.context["formato"] = Importacion.Formato.PDF
        elif cabecera.startswith(b"PK\x03\x04"):  # un .xlsx es un ZIP (si no es un Excel, falla al analizarlo)
            self.context["formato"] = Importacion.Formato.XLSX
        elif b"\x00" in cabecera:  # un CSV es texto: un byte nulo delata un binario (xls antiguo, imagen…)
            raise serializers.ValidationError("Sube el extracto en CSV, Excel (.xlsx) o PDF.")
        else:
            self.context["formato"] = Importacion.Formato.CSV
        return archivo

    def validate(self, datos):
        datos["formato"] = self.context.pop("formato")
        if datos.get("perfil") and datos["formato"] == Importacion.Formato.PDF:
            raise serializers.ValidationError({"perfil": "Los perfiles son para CSV y Excel."})
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
            "perfil",
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
            "categoria",
            "movimiento",
        ]
        read_only_fields = fields


class CambiarFilaSerializer(DelHogarMixin, serializers.Serializer):
    campos_del_hogar = {"categoria": Categoria}
    categoria = serializers.PrimaryKeyRelatedField(queryset=Categoria.objects.none(), allow_null=True)


class ConfirmarImportacionSerializer(serializers.Serializer):
    separar = serializers.ListField(child=serializers.IntegerField(), required=False, default=list, max_length=5000)

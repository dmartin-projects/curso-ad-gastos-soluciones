# usuarios/managers.py
from django.contrib.auth.base_user import BaseUserManager


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _crear(self, email, password, **extra):
        if not email:
            raise ValueError("El email es obligatorio")
        email = self.normalize_email(email)
        usuario = self.model(email=email, **extra)
        usuario.set_password(password)  # ⚠️ nunca usuario.password = password
        usuario.save(using=self._db)
        return usuario

    def get_by_natural_key(self, email):
        # Lo usa el login (ModelBackend): "Ana@Example.com" entra en la cuenta "ana@example.com".
        # Hay como mucho una: la constraint usuario_email_unico_sin_mayusculas lo garantiza.
        return self.get(email__iexact=email)

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._crear(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        if not extra["is_staff"] or not extra["is_superuser"]:
            raise ValueError("Un superusuario necesita is_staff e is_superuser")
        return self._crear(email, password, **extra)

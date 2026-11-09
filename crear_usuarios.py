
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from tickets.models import Settings

User = get_user_model()

# Crear grupos
grupo_tecnico, _ = Group.objects.get_or_create(name="Tecnico")
grupo_admin, _ = Group.objects.get_or_create(name="Administrador")

# Datos de prueba
usuarios = [
    ("usuario01", "Carlos", "carlos@tixai.test", "usuario"),
    ("usuario02", "Maria", "maria@tixai.test", "usuario"),
    ("usuario03", "Andres", "andres@tixai.test", "usuario"),
    ("usuario04", "Valentina", "valentina@tixai.test", "usuario"),
    ("tecnico01", "Javier", "javier@tixai.test", "tecnico"),
    ("tecnico02", "Camila", "camila@tixai.test", "tecnico"),
    ("tecnico03", "Diego", "diego@tixai.test", "tecnico"),
    ("admin01", "Administrador Principal", "admin01@tixai.test", "admin"),
    ("admin02", "Administrador Secundario", "admin02@tixai.test", "admin"),
]

password = "Tixai123"

for username, nombre, email, tipo in usuarios:
    user, creado = User.objects.get_or_create(
        username=username,
        defaults={
            "first_name": nombre,
            "email": email,
        }
    )

    if creado:
        user.set_password(password)
        user.save()

    if tipo == "tecnico":
        user.groups.add(grupo_tecnico)

    elif tipo == "admin":
        user.is_staff = True
        user.is_superuser = True
        user.save()
        user.groups.add(grupo_admin)

    Settings.objects.get_or_create(
        usuario=user,
        defaults={
            "id_perfil": f"PER{user.pk:07d}"
        }
    )

    print(f"{username}: {'Creado' if creado else 'Ya existía'}")

print("\nCarga de usuarios finalizada.")

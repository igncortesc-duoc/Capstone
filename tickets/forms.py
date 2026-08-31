from django import forms
from django.contrib.auth.models import User


class RegistroForm(forms.Form):
    nombre = forms.CharField(max_length=100)
    apellido = forms.CharField(max_length=100)
    correo = forms.EmailField(max_length=100)
    telefono = forms.CharField(max_length=20, required=False)
    password = forms.CharField(widget=forms.PasswordInput, min_length=8)
    password2 = forms.CharField(
        widget=forms.PasswordInput,
        label="Confirmar contraseña"
    )

    def clean_correo(self):
        correo = self.cleaned_data['correo']
        if User.objects.filter(username=correo).exists():
            raise forms.ValidationError("Ya existe una cuenta con este correo.")
        return correo

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get('password')
        password2 = cleaned.get('password2')
        if password and password2 and password != password2:
            self.add_error('password2', "Las contraseñas no coinciden.")
        return cleaned
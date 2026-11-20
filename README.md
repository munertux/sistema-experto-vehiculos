# Sistema experto de diagnóstico de fallas en vehículos

Proyecto de la asignatura Sistemas Expertos, Universidad Manuela Beltrán (Ingeniería de Software).
Autores: Sebastián Felipe Araque Pérez, Luilly Steven Perea Vivas y Thomas Leonardo Castillo Castro.

Aplicación web en Flask con PostgreSQL. Tiene tres capas: presentación (`main.py`, `app/templates`, `app/static`),
lógica (`app/logica`: motor de inferencia, memoria de trabajo y servicio de diagnóstico) y datos (`app/datos`).

## Base de datos

```bash
createdb sistema_experto_vehiculos
psql -d sistema_experto_vehiculos -f sql/01_esquema.sql
psql -d sistema_experto_vehiculos -f sql/02_conocimiento.sql
```

## Ejecución local

```bash
pip install -r requirements.txt
export DATABASE_URL="postgresql://usuario:clave@localhost:5432/sistema_experto_vehiculos?sslmode=disable"
export SE_CLAVE_HASH="<hash generado con werkzeug.security.generate_password_hash>"
export COOKIE_SEGURA=0
export FLASK_DEBUG=1          # o SE_ENTORNO=desarrollo, o defina SECRET_KEY
python main.py   # http://127.0.0.1:8000
```

Pruebas: `SE_ENTORNO=pruebas` lo fija `pruebas/conftest.py`; basta `pytest -q pruebas`.

## Despliegue en Azure App Service

Comando de inicio (Configuración → Configuración general → Comando de inicio):

```bash
gunicorn --bind=0.0.0.0 --timeout 120 --workers 2 --threads 4 main:app
```

- Varios workers son seguros: la memoria de trabajo de cada consulta se reconstruye desde la base de datos.
- `gunicorn.conf.py` (se carga solo desde la raíz) oculta la cabecera `Server: gunicorn`.

Variables de entorno:

| Variable | Obligatoria | Uso |
|----------|-------------|-----|
| `SECRET_KEY` | **Sí** | Firma de sesiones y CSRF. Sin ella la app **no arranca** en producción. Genérela con `python -c "import secrets; print(secrets.token_hex(32))"` y debe ser la misma en todos los workers e instancias. |
| `DATABASE_URL` o `AZURE_POSTGRESQL_CONNECTIONSTRING` | Sí | Conexión a PostgreSQL. |
| `COOKIE_SEGURA` | No (por defecto `1`) | Cookie de sesión solo por HTTPS. |
| `PROXY_SALTOS` | No (por defecto `1`) | Proxies de confianza para `X-Forwarded-For`/`-Proto` (Azure antepone uno). `0` si el servidor queda expuesto sin proxy. |

Controles de seguridad de la capa web (`app/web/seguridad.py`): límite por IP de POST a `/login` (20 cada 5 min) y a `/cuenta/clave` (10 cada 5 min), tope de 5 fallos de la contraseña actual por usuario cada 15 min, HSTS bajo HTTPS, Content-Security-Policy sin `'unsafe-inline'` en scripts (todo el JS está en `app/static`; D3 solo desde cdnjs con SRI) y mensaje de ingreso único que no revela qué usuarios existen. El límite vive en la memoria de cada worker: con 2 workers el máximo efectivo por IP es el doble.

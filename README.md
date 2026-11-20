# Sistema experto de diagnóstico de fallas en vehículos

Proyecto de la asignatura **Sistemas Expertos** de la Universidad Manuela Beltrán (Ingeniería de Software).

Autores: Sebastián Felipe Araque Pérez, Luilly Steven Perea Vivas y Thomas Leonardo Castillo Castro.

**Aplicación en producción (Azure):** https://app-se-vehiculos-umb26-dccrctbwfdfyh0c8.westus2-01.azurewebsites.net

---

## ¿Qué es?

Es un sistema experto que ayuda a una persona a descubrir **qué le puede estar fallando a su vehículo**, sin necesidad de saber de mecánica. Funciona como lo haría un técnico con experiencia: hace preguntas sobre los síntomas, una a la vez, y según cada respuesta decide qué preguntar después, hasta llegar a un diagnóstico probable.

Al final, el sistema muestra:

- la **falla más probable** y otras posibles,
- qué tan seguro está de cada una (**certeza** de 0 a 100 %),
- qué tan **urgente** es (por ejemplo, «No debe seguir usándose» o «Revisión prioritaria»),
- una **recomendación** concreta,
- y una **explicación** de cómo llegó a esa conclusión.

Es una orientación preliminar con fines académicos.

## ¿Por qué es un sistema experto y no un simple formulario?

Un formulario hace siempre las mismas preguntas en el mismo orden. Este sistema razona:

- **Tiene una base de conocimiento** separada del programa: 24 áreas del vehículo, 92 preguntas, 68 fallas posibles (hipótesis) y 111 reglas, todas guardadas en PostgreSQL. Se pueden ampliar sin tocar el código.
- **Tiene un motor de inferencia** que, con cada respuesta, actualiza el puntaje de cada falla posible y escoge la **siguiente pregunta más útil**: la que más ayuda a confirmar o descartar la falla que va ganando.
- **Combina varias pistas a la vez.** Algunas reglas exigen dos o más condiciones («si hay humo azul **y** baja el nivel de aceite…») o la ausencia de un síntoma («…**y no** se escucha chirrido de correa»).
- **Encadena conclusiones.** Una regla puede concluir un hecho intermedio (por ejemplo, «el sistema de carga está fallando») que a su vez activa otras reglas más específicas.
- **Usa los testigos del tablero y los códigos OBD-II** como evidencia: marcar el testigo de ABS o escribir el código `C0035` ya orienta el diagnóstico desde el principio.
- **Sabe cuándo detenerse:** cuando una falla está suficientemente respaldada, deja de preguntar. Y si nada se confirma, responde «Sin falla identificada» en lugar de inventar un diagnóstico.
- **Se explica a sí mismo:** en cada pregunta se puede abrir «¿Por qué me pregunta esto?» y, en el resultado, «¿Cómo llegó a esta conclusión?», que muestra paso a paso las reglas que se activaron.

## El árbol de decisión

**Archivo:** [`docs/arbol_decision.html`](docs/arbol_decision.html). Descárguelo y ábralo con doble clic en cualquier navegador; funciona sin internet. También está dentro de la aplicación, en la ruta `/arbol`.

El árbol de decisión es un **mapa de todos los caminos de preguntas que puede seguir el sistema** en cada área del vehículo. No se dibujó a mano: se generó **simulando el propio motor de inferencia** con todas las combinaciones de respuestas posibles, así que muestra exactamente lo que hace la aplicación.

Cómo se lee:

- Cada **nodo** (rectángulo) es una **pregunta** que el sistema le hace al usuario. El primero de cada área es la pregunta de entrada («¿Observa algún problema en…?»).
- De cada pregunta salen **ramas**: la **verde** es la respuesta «Sí / Probablemente sí» y la **gris** es «No / Probablemente no».
- Siguiendo las ramas se llega a una **hoja**, que es el **diagnóstico** donde el sistema se detiene. La hoja muestra la falla, la certeza y el nivel de atención.
- Hay hojas especiales de **«Sin falla identificada»**, cuando las respuestas no respaldan ninguna falla.
- El **grosor** de una rama indica cuántos caminos pasan por ella.

En total el árbol tiene **788 nodos: 382 preguntas y 406 diagnósticos**.

Qué se puede hacer en la página:

- Escoger el **área** del vehículo (arranque, frenos, motor y desempeño…).
- **Buscar** una falla y ver por qué preguntas se llega a ella.
- Usar el **recorrido guiado**: se escoge un camino y con «Siguiente» se ve, pregunta por pregunta, cómo el motor llega al diagnóstico.
- Expandir, contraer y ajustar la vista.

Ejemplo, en el área «Arranque del vehículo»: si el usuario responde **Sí** a que hay un problema de arranque, **Sí** a que el vehículo no arranca y no se escucha ningún ruido eléctrico, y **No** al clic repetido de los bornes, el sistema concluye «Batería completamente descargada o sulfatada» con 50 % de certeza.

El árbol se construyó sin testigos del tablero ni códigos OBD. Con ellos, el camino real puede ser más corto, porque el sistema ya parte con evidencia.

## Cómo usar la aplicación

Cada cuenta tiene un rol, y cada rol ve su propia parte:

| Rol | Qué hace |
|---|---|
| **Consultante** | Registra sus vehículos, hace **nuevas consultas** al sistema experto y revisa su historial. |
| **Ingeniero del conocimiento** | Mantiene la base de conocimiento: áreas, preguntas, hipótesis y reglas. |
| **Administrador** | Gestiona usuarios, revisa la auditoría y hace respaldos. |

Para hacer una consulta hay que entrar con una cuenta de **consultante**. Luego se elige **Nueva consulta**, el vehículo y el área, opcionalmente los testigos encendidos y un código OBD, y se responden las preguntas.

## Modelo de datos

El diagrama de la base de datos está en [`docs/modelo_relacional.png`](docs/modelo_relacional.png) (también en [PDF](docs/modelo_relacional.pdf)). Tiene 18 tablas y 21 relaciones, agrupadas por color:

- **Usuarios** (azul): roles, cuentas, empleados, consultantes y vehículos.
- **Atención** (naranja): cada consulta, sus respuestas (la memoria de trabajo) y sus diagnósticos.
- **Base de conocimiento** (verde): áreas, preguntas, hipótesis y reglas.
- **Extensión del motor** (morado): condiciones compuestas de las reglas, hechos intermedios, relación de testigos y códigos OBD con las fallas, y parámetros del motor.

## Cómo está hecho

Aplicación web en **Flask** (Python 3.12) con **PostgreSQL 16**, organizada en tres capas:

- **Presentación** (`app/web`, `app/templates`, `app/static`): páginas, formularios y API JSON.
- **Lógica** (`app/logica`): motor de inferencia, memoria de trabajo y servicios.
- **Datos** (`app/datos`): DAO y repositorios; son los únicos que ejecutan SQL.

Otras carpetas:

- `sql/`: esquema y conocimiento, en el orden en que se aplican (01 → 11).
- `pruebas/`: 250 pruebas automáticas, incluidos 31 casos de diagnóstico completos.
- `scripts/`: aplicar migraciones, crear usuarios, generar el árbol y exportar respaldos.
- `docs/`: árbol de decisión, modelo relacional y documentación técnica.
- `exportes/`: imágenes del árbol de tres áreas (PNG y SVG).

## Ejecutarlo en local

```bash
pip install -r requirements.txt

createdb sistema_experto_vehiculos
export DATABASE_URL="postgresql://usuario:clave@localhost:5432/sistema_experto_vehiculos?sslmode=disable"
psql -d sistema_experto_vehiculos -f sql/01_esquema.sql
psql -d sistema_experto_vehiculos -f sql/02_conocimiento.sql
python scripts/aplicar_sql.py          # aplica sql/05 … sql/11

# crea una cuenta; si no se da --clave, genera una aleatoria y la muestra una sola vez
python scripts/crear_usuario.py admin administrador "Administrador del sistema"
python scripts/crear_usuario.py consultante1 consultante "Carlos Rodríguez"

export COOKIE_SEGURA=0
export FLASK_DEBUG=1
python main.py                         # http://127.0.0.1:8000
```

Pruebas: `pytest -q pruebas`. Usan un esquema aparte, así que no tocan los datos.

## Despliegue en Azure

Corre en **Azure App Service** (Linux, Python 3.12) con una base **Azure Database for PostgreSQL – servidor flexible**.

Comando de inicio:

```bash
gunicorn --bind=0.0.0.0 --timeout 120 --workers 2 --threads 4 main:app
```

Variables de entorno:

| Variable | Obligatoria | Para qué sirve |
|---|---|---|
| `SECRET_KEY` | Sí | Firma las sesiones. Sin ella la aplicación no arranca en producción. |
| `DATABASE_URL` | Sí | Conexión a PostgreSQL. |
| `COOKIE_SEGURA` | No (por defecto `1`) | Envía la cookie de sesión solo por HTTPS. |
| `PROXY_SALTOS` | No (por defecto `1`) | Número de proxies de confianza (Azure pone uno delante). |

Se pueden usar varios procesos de gunicorn sin problema, porque la memoria de trabajo de cada consulta se reconstruye desde la base de datos.

**Seguridad:** límite de intentos de inicio de sesión por IP, mensaje de error que no revela qué usuarios existen, HSTS, política de seguridad de contenido (CSP), contraseñas guardadas solo como hash, y permisos por rol en cada página.

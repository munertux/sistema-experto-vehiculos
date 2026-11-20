# -*- coding: utf-8 -*-
"""Limitador de peticiones en memoria con ventana deslizante (H-01).

Sin dependencias externas. El estado vive en cada proceso de gunicorn:
con N workers el limite efectivo por IP es como maximo N veces el
configurado, lo que sigue frenando la fuerza bruta y el password spraying.
Si la app escala a varias instancias, conviene pasar a Flask-Limiter con
un almacenamiento compartido (Redis).
"""
import collections
import ipaddress
import threading
import time

# Tope de claves distintas en memoria (evita que un atacante con muchas IP
# haga crecer el diccionario sin limite).
MAX_CLAVES = 20000


class LimitadorVentana:
    def __init__(self, reloj=time.monotonic):
        self._reloj = reloj
        self._eventos = collections.defaultdict(collections.deque)
        self._lock = threading.Lock()

    def _purgar(self, q, ventana, ahora):
        while q and ahora - q[0] >= ventana:
            q.popleft()

    def _recortar(self, ventana_max):
        """Elimina claves vacias o vencidas cuando hay demasiadas."""
        ahora = self._reloj()
        for clave in list(self._eventos):
            q = self._eventos[clave]
            self._purgar(q, ventana_max, ahora)
            if not q:
                del self._eventos[clave]
        if len(self._eventos) > MAX_CLAVES:      # sigue lleno: se descartan las mas antiguas
            orden = sorted(self._eventos, key=lambda c: self._eventos[c][-1])
            for clave in orden[: len(self._eventos) - MAX_CLAVES]:
                del self._eventos[clave]

    def excedido(self, clave, maximo, ventana):
        """True si ``clave`` ya alcanzo ``maximo`` eventos en ``ventana`` segundos
        (no registra un evento nuevo)."""
        with self._lock:
            q = self._eventos.get(clave)
            if not q:
                return False
            self._purgar(q, ventana, self._reloj())
            return len(q) >= maximo

    def registrar(self, clave, ventana):
        with self._lock:
            if clave not in self._eventos and len(self._eventos) >= MAX_CLAVES:
                self._recortar(ventana)
            self._eventos[clave].append(self._reloj())

    def consumir(self, clave, maximo, ventana):
        """Registra un evento si hay cupo. Devuelve True si la peticion se
        permite y False si se excedio el limite."""
        with self._lock:
            if clave not in self._eventos and len(self._eventos) >= MAX_CLAVES:
                self._recortar(ventana)
            q = self._eventos[clave]
            ahora = self._reloj()
            self._purgar(q, ventana, ahora)
            if len(q) >= maximo:
                return False
            q.append(ahora)
            return True

    def reiniciar(self, clave):
        with self._lock:
            self._eventos.pop(clave, None)

    def segundos_restantes(self, clave, ventana):
        with self._lock:
            q = self._eventos.get(clave)
            if not q:
                return 0
            return max(1, int(ventana - (self._reloj() - q[0])) + 1)


def normalizar_ip(valor):
    """IP del cliente sin puerto. Azure App Service puede enviar en
    X-Forwarded-For valores como ``203.0.113.7:51234`` o ``[2001:db8::1]:443``;
    sin normalizar, cada conexion tendria una "IP" distinta y el limite por
    IP no serviria."""
    valor = (valor or "").strip()
    if not valor:
        return "desconocida"
    if valor.startswith("["):                      # [ipv6]:puerto
        valor = valor[1:].split("]", 1)[0]
    elif valor.count(":") == 1:                    # ipv4:puerto
        valor = valor.split(":", 1)[0]
    try:
        return str(ipaddress.ip_address(valor))
    except ValueError:
        return valor[:64]

# CANALES BEBE

Lista M3U generada automáticamente con los canales abiertos de **TUMM TV+** (web.tumm.tv), Costa Rica.

La lista se regenera sola cada 6 horas porque los enlaces de transmisión llevan tokens de corta duración.

## Uso en IPTV Smarters

Agregá una lista M3U con esta URL:

```
https://raw.githubusercontent.com/josueluz89/CANALES-BEBE/main/tummtv.m3u
```

## Cómo funciona

`generate_m3u.py` replica el flujo de la web de TUMM TV+:

1. Registro anónimo (`demo-login`, sin cuenta)
2. Lista de canales (`/api/player/channels`)
3. URL de stream por canal (`/api/player/streams`)
4. Arma el archivo `tummtv.m3u`

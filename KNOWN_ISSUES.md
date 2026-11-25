# Limitaciones conocidas — Tipo v0.3.1-beta.1

## Alcance funcional

- Versión orientada a monografías impresas modernas.
- ISBD es una vista derivada solo lectura.
- MARCXML es una propuesta descriptiva inicial, no un registro catalográfico completo.
- No se generan campos de autoridad ni puntos de acceso autorizados.
- La descripción física suele requerir revisión manual.
- La calidad depende de las imágenes aportadas, especialmente portada y verso de portada.

## Riesgos residuales de seguridad y privacidad

- **Salida a internet del contenedor de la aplicación.** `tipo-app` está en la
  red por defecto de Docker y podría salir a internet. El código solo habla con
  Ollama, con un cliente HTTP que ignora proxies y redirecciones. Docker no
  publica puertos de contenedores que estén solo en redes `internal`, así que
  aislarlo del todo exigiría otro diseño de red.
- **Contenedor de Ollama.** Corre como root dentro del contenedor (sin
  capacidades y con `no-new-privileges`) y sin sistema de ficheros de solo
  lectura. Tiene salida a internet porque descarga los modelos.
- **Datos en reposo sin cifrar.** Usuarios, lotes y resultados están en el
  volumen Docker `tipo-data` sin cifrado propio; dependen del cifrado del disco
  del equipo.
- **Nombres de archivo en lotes incógnito.** La lista de libros de un lote guarda
  los nombres de los ficheros para que el usuario pueda distinguirlos. En modo
  incógnito no se guardan huellas SHA-256 ni originales, pero esos nombres se
  conservan con el lote hasta que caduca o se borra.
- **Tokens CSRF globales.** Se emiten hasta 16 tokens válidos a la vez,
  compartidos por todas las sesiones. Un proceso local puede pedir tokens y
  hacer que caduquen los de una pestaña abierta (errores 403 hasta recargar).
- **Bloqueo de inicio de sesión por cliente.** Dentro de Docker todas las
  peticiones llegan desde la pasarela de la red, de modo que el límite «por
  cliente» se comparte entre todos los usuarios del equipo.
- **Instalaciones que actualizan desde versiones anteriores.** Un `.env` antiguo
  puede mantener `TIPO_LOTE_RETENCION_DIAS=0` (sin límite) y
  `TIPO_LOTE_CONSERVAR_ORIGINALES=true`. El instalador no los cambia para no
  borrar datos sin consentimiento; hay que editarlos a mano.
- **Fuentes tipográficas opcionales.** `frontend/static/fonts/descargar-fuentes.*`
  descarga de la rama principal de sus repositorios, sin suma de comprobación.
  La interfaz funciona sin ellas.

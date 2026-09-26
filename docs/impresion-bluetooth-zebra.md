# Imprimir etiquetas al pesar: Zebra ZQ520 por Bluetooth desde la pantalla de pesar

Nació del pedido 1357 (2026-09-25): las 31 etiquetas se imprimieron juntas al
final y se pegaron buscando la caja por peso, y varias quedaron cruzadas entre
dos chorizos de peso casi igual. Con esto la etiqueta sale al pie de la
báscula, caja por caja, sin salir de la pantalla de pesar y sin la app de Zebra.

## Qué hace la app

- `GET /cajas/<id>/etiqueta.zpl` devuelve la etiqueta 4x2 de una caja en ZPL
  (`utils/zpl.py`), más el logo como objeto gráfico para la memoria de la
  impresora.
- `static/js/zebra_ble.js` habla con la Zebra por Web Bluetooth (servicio
  `38eb4a80-…`, característica `38eb4a82-…`, paquetes de 20 bytes con
  confirmación, el protocolo que documenta Zebra para sus Link-OS).
- En la pantalla de pesar aparece la barra «Impresora» solo cuando el
  navegador tiene Web Bluetooth (Chrome en Android, incluida la app instalada
  en pantalla de inicio). En iPhone no aparece: Safari no tiene Web Bluetooth
  y ahí la etiqueta sigue saliendo por el botón «Imprimir etiqueta» (PDF).
- Con la impresora conectada y «Imprimir al pesar» activo, cada caja
  registrada imprime su etiqueta sola. El botón «Imprimir etiqueta» de la
  confirmación y del modal de cada caja también imprime por Bluetooth.
- El logo se carga una sola vez por conexión (unos 7 KB, 10 a 15 segundos la
  primera vez) y queda en la memoria flash `E:` de la impresora; las etiquetas
  solo lo invocan por nombre. Si el logo del cliente cambia, cambia el nombre
  y se vuelve a cargar solo.

## Camino recomendado: Zebra Browser Print en el Android (Bluetooth clásico)

Zebra documenta (artículo 000015127) que el Bluetooth de baja energía de sus
impresoras es para configurarlas, no para imprimir, y en la ZQ520 del
almacén (radio 6.0.1, firmware V76.20.22Z, el más reciente) el modo de baja
energía ni siquiera se puede activar: `bluetooth.le.controller_mode` queda
en `classic` haga lo que se haga. Lo que Zebra sí soporta oficialmente para
imprimir desde una página web es **Zebra Browser Print**, una app que corre
en el mismo Android, se empareja con la impresora por Bluetooth clásico y
expone un servicio local (`http://localhost:9100`, `https://localhost:9101`)
al que la página le manda el ZPL. La lista oficial de impresoras soportadas
incluye la ZQ520. `static/js/zebra_browser_print.js` habla con ese servicio;
la pantalla de pesar lo intenta primero y solo si no responde pasa a Web
Bluetooth.

1. En el Android, emparejar la ZQ520 en Ajustes > Bluetooth (Bluetooth
   clásico, como con cualquier auricular).
2. Instalar **Zebra Browser Print** para Android (Google Play, gratis).
   Abrirla, dar los permisos de Bluetooth y ubicación, y comprobar que lista
   la ZQ520 como impresora. Marcarla como predeterminada si lo ofrece.
3. Dejar la app abierta o en segundo plano. Abrir PesosApp en Chrome y entrar
   a la pantalla de pesar. La primera vez que la página habla con Browser
   Print, la app pregunta si se acepta ese sitio: aceptar.
4. Tocar «Conectar». Debe aparecer «Impresora: <nombre de la ZQ520>». Tocar
   «Prueba».
5. Con «Imprimir al pesar» activo, registrar la caja: la etiqueta sale sola.

Si «Conectar» dice que Browser Print no responde: la app no está abierta,
no tiene la impresora emparejada, o Chrome no pudo llegar a
`localhost:9100`. Abrir `http://localhost:9100/available` en Chrome del
mismo Android: debe mostrar un JSON con la impresora. Si la página está
en HTTPS y Chrome bloquea el puerto 9100, abrir una vez
`https://localhost:9101/` y aceptar el certificado de Browser Print.

Browser Print no existe para iPhone. En iPhone la etiqueta sigue saliendo
por «Imprimir etiqueta» y la app de Zebra, o se pesa con el Android.

## Camino alternativo: Web Bluetooth (baja energía)

Solo para impresoras cuyo modo de baja energía sí esté disponible (Zebra lo
expone en modelos de escritorio e industriales ZD/ZT recientes) y con la
salvedad de que Zebra no lo considera un canal de impresión soportado.

## Puesta en marcha en el almacén (Web Bluetooth)

1. **Impresora.** ZQ520 encendida, con rollo de etiquetas 4x2 troqueladas. En
   Zebra Setup Utilities (o Printer Setup Utility en el teléfono) confirmar
   que el Bluetooth de baja energía está activo: `bluetooth.le.controller_mode`
   en `both` o `le`. Si la impresora ya se usa desde la app de Zebra por
   Bluetooth clásico, `both` mantiene las dos cosas.
2. **Teléfono Android.** Chrome actualizado, Bluetooth y ubicación encendidos
   (Android exige ubicación para escanear Bluetooth). Abrir PesosApp por HTTPS
   (Web Bluetooth no funciona en HTTP).
3. **Primera conexión.** En la pantalla de pesar tocar «Conectar». Chrome
   muestra las impresoras Zebra cercanas; elegir la ZQ520. Si no aparece
   ninguna, tocar «Buscar todos» y elegirla de la lista completa.
4. **Prueba.** Tocar «Prueba»: debe salir una etiqueta que dice «PesosApp,
   Impresora conectada».
5. **Pesar.** Con «Imprimir al pesar» activo, registrar la caja: la etiqueta
   sale sola y se pega antes de bajar la caja de la báscula.

La conexión dura mientras la pestaña esté abierta y la impresora encendida.
Si se desconecta, la barra lo avisa y «Conectar» la vuelve a atar.

## Si algo falla

- «No se eligió ninguna impresora»: se cerró el selector de Chrome sin elegir.
- «No se pudo conectar»: impresora apagada, fuera de alcance, o con el
  Bluetooth de baja energía desactivado (ver paso 1).
- Etiqueta en blanco o cortada: revisar que el rollo sea de etiquetas 4x2 y
  que el sensor de separación esté calibrado (calibración desde el menú de la
  impresora).
- Logo no sale: la impresora no tiene espacio en `E:` o rechazó el objeto;
  «Desconectar» y «Conectar» lo vuelve a cargar.

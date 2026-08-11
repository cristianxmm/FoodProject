#!/bin/bash

# 1. Esperar a que el servidor responda
until curl -s http://localhost:5000 > /dev/null; do
  sleep 1
done

# 2. Ocultar cursor
unclutter -idle 1 -root &

# 3. Abrir Pantalla Empleados
firefox -P kiosk_emp --no-remote --kiosk "http://localhost:5000" &
sleep 3

# 4. Abrir Pantalla Cocina
firefox -P kiosk_cocina --no-remote --kiosk "http://localhost:5000/lnc" &

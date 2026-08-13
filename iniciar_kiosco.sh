#!/bin/bash

# 1. Esperar a que el servidor responda
until curl -s http://localhost:5000 > /dev/null; do
  sleep 1
done

# 2. Ocultar cursor del mouse
unclutter -idle 1 -root &

# 3. Lanzar Firefox en Kiosco REAL con perfil independiente
firefox -P kiosk_split --no-remote --kiosk "http://localhost:5000/kiosk_split" &
#!/usr/bin/env bash

flet pack chronicler/__main__.py \
            --name Chronicler \
            --icon assets/icon.png \
            --add-data "assets:assets" \
            --add-data "chronicler/migrations:chronicler/migrations" \
            --add-data "chronicler/webclient/src:chronicler/webclient/src" \
            --hidden-import aiosqlite \
            --hidden-import re._parser

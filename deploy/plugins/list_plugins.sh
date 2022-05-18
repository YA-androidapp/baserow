#!/bin/bash
# Bash strict mode: http://redsymbol.net/articles/unofficial-bash-strict-mode/
set -euo pipefail


BASEROW_PLUGIN_DIR=${BASEROW_PLUGIN_DIR:-/baserow/plugins}

echo "Listing installed Baserow Plugins:"
for plugin_folder in "$BASEROW_PLUGIN_DIR"/*; do
    if [[ -d "$plugin_folder" ]]; then
        plugin_name="$(basename -- "$plugin_folder")"
        echo " - $plugin_name"
        if [[ -f "$plugin_folder/baserow_plugin_info.json" ]]; then
            plugin_info="$(cat "$plugin_folder/baserow_plugin_info.json")"
            description=$(echo "$plugin_info" | python3 -c "import sys, json; print(json.load(sys.stdin).get('description', ''))" || "")
            echo "      $description"
        fi
    fi
done
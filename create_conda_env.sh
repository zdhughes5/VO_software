#!/bin/bash

# Script to create a new conda environment from requirements.txt
# Usage: ./create_conda_env.sh <environment_name>

ENV_NAME=${1:-veritas}

echo "Creating conda environment: $ENV_NAME"
echo "Reading package names from requirements.txt..."

# Map of pip package names to conda package names (or skip if not in conda)
declare -A PACKAGE_MAP=(
    ["PyQt5"]=""
    ["PyQt6"]="pyqt"
    ["pyqt6_sip"]=""
    ["ROOT"]="root"  # Skip - not typically available in conda
    ["msgpack_python"]=""  # Skip - old package
    ["msgpack_numpy"]=""  # Skip - not in conda-forge
    ["PyMySQL"]="pymysql"
)

# Extract package names from requirements.txt and map them
PACKAGES=""
while IFS='==' read -r pkg version; do
    pkg=$(echo "$pkg" | xargs)  # trim whitespace
    
    # Check if package needs mapping
    if [[ -n "${PACKAGE_MAP[$pkg]+isset}" ]]; then
        mapped="${PACKAGE_MAP[$pkg]}"
        if [[ -n "$mapped" ]]; then
            PACKAGES="$PACKAGES $mapped"
        fi
    else
        # Use package name as-is (lowercase for conda)
        PACKAGES="$PACKAGES $(echo "$pkg" | tr '[:upper:]' '[:lower:]')"
    fi
done < requirements.txt

echo "Packages to install: $PACKAGES"
echo ""

# Create the environment with Python and packages from conda-forge
conda create -n "$ENV_NAME" -c conda-forge python $PACKAGES -y

echo ""
echo "Environment '$ENV_NAME' created successfully!"
echo "To activate it, run: conda activate $ENV_NAME"

#!/bin/bash


SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

function drypipe {
    pixi run --manifest-path=$SCRIPT_DIR/pixi.toml python3 -u -m dry_pipe.cli "$@"    
}
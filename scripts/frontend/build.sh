#!/bin/bash
cd /home/jwjang/work/trader-ai/src/frontend
npm ci
VITE_ENV_DIR=/home/jwjang/work/trader-ai/config npm run build

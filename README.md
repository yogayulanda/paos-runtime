# PAOS Runtime

Portable runtime for PAOS (Personal AI Operating System).

## Architecture

PAOS separates runtime from user context.

Runtime:
- Telegram Bot
- Workers
- Digest Engine
- Context Router
- Memory Integration

Context:
- personal-context repository

## Structure

bot/
services/
context/
memory/
workers/

## Commands

/profile
/digest
/ops
/help

## Context

Configured through:

PAOS_CONTEXT_PATH

## Status

Early development.
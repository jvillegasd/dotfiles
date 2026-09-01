# Homebrew package manifest for macos.sh.
#
# Regenerate after installing or removing something:
#   brew bundle dump --describe --force --file=Brewfile
#
# macos.sh applies it with `brew bundle --file Brewfile`. harness/install.sh
# installs the AI clients and integrations it needs on its own, so it stays
# runnable without this file.

tap "anomalyco/tap"
tap "benbjohnson/litestream"
tap "gentleman-programming/tap"
tap "heroku/brew"
tap "libsql/sqld"
tap "ngrok/ngrok"
tap "retlehs/tap"
tap "steipete/tap"
tap "tursodatabase/tap"
tap "tw93/tap"
# Present on this machine only as dependencies, so `brew bundle dump` omitted
# them, but a fresh machine needs them: the previous installer named them
# explicitly. Installing them through `brew bundle` marks them installed on
# request, so the next dump keeps them and this block can go.
brew "git"
brew "make"
brew "ripgrep"
cask "font-jetbrains-mono-nerd-font"

# Official Amazon AWS command-line interface
brew "awscli"
# Install RubyGems as Homebrew formulae
brew "brew-gem"
# Statistics utility to count lines of code
brew "cloc"
# Cloudflare Tunnel client (formerly Argo Tunnel)
brew "cloudflared"
# Cryptographic recipes and primitives for Python
brew "cryptography"
# Simple, fast and user-friendly alternative to find
brew "fd"
# Play, record, convert, and stream select audio and video codecs
brew "ffmpeg"
# Libraries to talk to Microsoft SQL Server and Sybase databases
brew "freetds"
# TIFF library and utilities
brew "libtiff"
# New file format for still image compression
brew "jpeg-xl"
# GitHub command-line tool
brew "gh"
# Quickly rewrite git repository history
brew "git-filter-repo"
# Open source programming language to build simple/reliable/efficient software
brew "go"
# Improved top (interactive process viewer)
brew "htop"
# Image manipulation library
brew "jpeg"
# Interpreted, interactive, object-oriented programming language
brew "python@3.10"
# Implementation of JSON Schema for Python
brew "jsonschema", link: false
# Simple terminal UI for git commands
brew "lazygit"
# Library to render SVG files using Cairo
brew "librsvg"
# Deep clean and optimize your Mac
brew "mole"
# Incremental parsing library
brew "tree-sitter"
# Ambitious Vim-fork focused on extensibility and agility
brew "neovim"
# Open-source, cross-platform JavaScript runtime environment
brew "node"
# Data loading tool for PostgreSQL
brew "pgloader"
# General-purpose scripting language
brew "php"
# General-purpose scripting language
brew "php@8.2"
# Package compiler and linker metadata toolkit
brew "pkgconf"
# Fast, disk space efficient package manager
brew "pnpm"
# Object-relational database system
brew "postgresql@14"
# Python version management
brew "pyenv"
# Pyenv plugin to manage virtualenv
brew "pyenv-virtualenv"
# Python interface to Tcl/Tk
brew "python-tk@3.12"
# Python interface to Tcl/Tk
brew "python-tk@3.13"
# Interpreted, interactive, object-oriented programming language
brew "python@3.11"
# Interpreted, interactive, object-oriented programming language
brew "python@3.8"
# Better WHOIS and domain intelligence toolkit
brew "quien"
# Install various Ruby versions and implementations
brew "ruby-build"
# Ruby version manager
brew "rbenv"
# Rsync for cloud storage
brew "rclone"
# Standard unix software packaging tool
brew "rpm"
# Postgres development platform
brew "supabase"
# Display directories as trees (with optional color/HTML output)
brew "tree"
# Parser generator tool
brew "tree-sitter-cli"
# Extremely fast Python package installer and resolver, written in Rust
brew "uv"
# Tool for creating isolated virtual python environments
brew "virtualenv", link: false
# Internet file retriever
brew "wget"
# CLI for Git worktree management, designed for parallel AI agent workflows
brew "worktrunk"
# JavaScript package manager
brew "yarn"
# General-purpose lossless data-compression library
brew "zlib"
# The AI coding agent built for the terminal.
brew "anomalyco/tap/opencode", trusted: true
# Persistent memory for AI coding agents. Agent-agnostic, single binary, zero dependencies.
brew "gentleman-programming/tap/engram", trusted: true
# Audio utility
cask "background-music"
# OpenAI's coding agent that runs in your terminal
cask "codex"
cask "codexbar"
cask "font-monocraft"
# Terminal emulator that uses platform-native UI and GPU acceleration
cask "ghostty"
# Web browser
cask "google-chrome"
go "golang.org/x/tools/gopls"
go "honnef.co/go/tools/cmd/staticcheck"
uv "pre-commit"
npm "@google/gemini-cli"
npm "skills"

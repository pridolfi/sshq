# sshq: AI-assisted SSH wrapper

`sshq` is a drop-in replacement for standard `ssh` that brings the power of AI to offline embedded Linux targets. 

It seamlessly injects a lightweight, AI-powered query command (`q`) into your SSH session, allowing you to ask for complex shell commands without ever leaving your terminal or searching the web.

![usage](docs/images/usage.gif)

## Why `sshq`?

When working on embedded boards (like Yocto or Buildroot builds), you often face two problems:
1. The board has no internet access, so you can't run AI CLI tools directly on it.
2. Even if it did have internet, you **never** want to put your personal API keys on a target device.

`sshq` solves both.

## How it Works

1. **The Host Server:** When you run `sshq`, it spins up a lightweight local web server in the background on your laptop. This server securely holds your `GEMINI_API_KEY` and talks to the Gemini API.
2. **The Reverse Tunnel:** `sshq` wraps your standard `ssh` command and adds a reverse port forward to a random local port, creating a secure tunnel from the board back to your laptop.
3. **Transparent Injection:** During login, `sshq` passes a Python one-liner to the board (the `q` client script) and drops it into `~/.local/bin/q`, and immediately hands you an interactive shell.

## Prerequisites

* Python 3.9 or higher (on your host machine).
* A Gemini API key (get one from Google AI Studio or Google Cloud console).
* Python 3 installed on the target embedded board (standard library only; no external packages required).

## Installation

Using `pip`:

```bash
pip install git+https://github.com/pridolfi/sshq.git
```

(Note: You can also clone the repo and use `pip install -e .` if you plan to modify the code).

## Usage
1. Export your API key in your terminal (or add it to your `~/.bashrc` / `~/.zshrc`):

```bash
export GEMINI_API_KEY="your_api_key_here"
```

2. Connect to your board exactly as you normally would, just replace ssh with sshq:

```bash
sshq root@192.168.1.100
```
(Note: Any standard SSH flags, like `-i key.pem` or `-p 2222`, will work perfectly).

3. Once connected to the board, use the `q` command to ask for shell commands. The AI will suggest a command, print it in bold cyan, and ask if you want to run it:

```bash
$ q find the top 5 largest files in /var/log

find /var/log -type f -exec du -Sh {} + | sort -rh | head -n 5

Do you want to execute this command? [y/N] y

15M     /var/log/syslog
10M     /var/log/messages
8.2M    /var/log/kern.log
5.1M    /var/log/auth.log
2.3M    /var/log/dpkg.log

$ q extract the tarball archive.tar.gz to /tmp

tar -xzf archive.tar.gz -C /tmp

Do you want to execute this command? [y/N] n
$
```

## File Analysis with `--analyze`

In addition to command suggestions, `sshq` provides AI-powered file analysis capabilities. Use the `--analyze` flag with the `q` command to ask questions about files on your embedded board.

![analyze](docs/images/analyze.gif)

### Usage

```bash
q --analyze <file_path> <your_question>
```

### Example

```
$ q --analyze /proc/cpuinfo What CPU architecture and features does this system have? Explain them briefly.
The system has the following CPU architecture and features:

CPU Architecture:
- 8: This indicates an ARMv8-A architecture, which is a 64-bit instruction set architecture.

CPU Features:
- fp: Floating Point - Hardware support for floating-point arithmetic.
- asimd: Advanced SIMD (Single Instruction, Multiple Data) - Provides parallel processing capabilities for multimedia and signal processing.
- evtstrm: Event Stream - Support for performance monitoring unit (PMU) event streams.
- aes: Advanced Encryption Standard - Hardware acceleration for AES encryption and decryption.
- pmull: Polynomial Multiply - Hardware support for polynomial multiplication, often used in cryptographic operations like GCM.
- sha1: Secure Hash Algorithm 1 - Hardware acceleration for SHA-1 hashing.
- sha2: Secure Hash Algorithm 2 - Hardware acceleration for SHA-2 (SHA-256, SHA-512) hashing.
- crc32: Cyclic Redundancy Check 32-bit - Hardware acceleration for CRC32 calculations, used for data integrity checks.
- atomics: Atomic operations - Hardware support for atomic memory operations, crucial for multi-threaded programming.
- fphp: Half-precision Floating Point - Support for 16-bit half-precision floating-point numbers.
- asimdhp: Half-precision Advanced SIMD - SIMD operations that can operate on half-precision floating-point data.
- cpuid: CPU ID - Instruction to read CPU identification and feature registers.
- asimdrdm: Advanced SIMD Rounding Double Multiply Accumulate - SIMD instructions for rounding double multiply accumulate operations.
- lrcpc: Load-acquire/Release Consistency Point Cache - Support for Load-acquire/Release instructions for memory consistency.
- dcpop: Data Cache Zero - Instruction to zero a cache line without loading it from memory.
- asimddp: Advanced SIMD Dot Product - SIMD instructions for dot product operations, useful for machine learning workloads.
```

## Environment variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `GEMINI_API_KEY` | Yes | — | Your Gemini API key. Used by the local server to call the Gemini API. |
| `SSHQ_GEMINI_MODEL` | No | `gemini-2.5-flash` | Gemini model used for command suggestions. You can also use `gemini-2.5-flash-lite`, which typically offers a higher quota. |

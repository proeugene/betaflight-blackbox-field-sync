# Contributing to LogFalcon

Thanks for wanting to help. LogFalcon is a small focused tool — contributions that keep it simple and reliable are welcome.

## Ways to contribute

- **Report a bug** — use the [Bug Report](.github/ISSUE_TEMPLATE/bug_report.md) template
- **Request a feature** — use the [Feature Request](.github/ISSUE_TEMPLATE/feature_request.md) template
- **Confirm your FC works** — fill in the [Hardware Compatibility](.github/ISSUE_TEMPLATE/hardware_compat.md) template; every confirmed board helps other pilots
- **Submit a fix** — open a PR (see below)

## Development setup

**Requirements:** Go 1.23+, Linux or macOS.

```bash
git clone https://github.com/proeugene/logfalcon.git
cd logfalcon
go test -race ./...   # all tests should pass
go build ./cmd/logfalcon
```

The binary targets ARM6 (Pi Zero W) and ARM64 (Pi Zero 2 W). Cross-compile with:

```bash
GOARCH=arm GOARM=6 GOOS=linux go build -o logfalcon-armv6 ./cmd/logfalcon
GOARCH=arm64 GOOS=linux go build -o logfalcon-arm64 ./cmd/logfalcon
```

To build the full SD card image you need Linux and Docker (pi-gen runs in a container):

```bash
cd pi-gen
./build.sh
```

## Submitting a pull request

1. Fork the repo and create a branch from `main`
2. Make your change and run `go test -race ./...` — all tests must pass
3. If you changed hardware behaviour, note which FC board and firmware you tested on
4. Open a PR — fill in the checklist in the PR template

## Scope

LogFalcon is deliberately scoped to **internal SPI flash blackbox** on Betaflight and iNav FCs. It does not read FC-side SD card logs over MSP and is not a general MSP library. PRs that expand scope significantly will be discussed first.

## Code style

Standard `gofmt` formatting. Run `go vet ./...` before submitting. No external linter config is required.

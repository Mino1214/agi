"""Entry point for the Crypto Regime Map server."""

from __future__ import annotations

import argparse

from visualizer import serve


def main() -> int:
    parser = argparse.ArgumentParser(description="Serve the crypto regime map")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8788)
    args = parser.parse_args()
    print(f"crypto_regime_map http://{args.host}:{args.port}", flush=True)
    serve(host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

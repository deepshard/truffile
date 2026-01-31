# Accessing Inference APIs on the Truffle

The Truffle currently uses its own non-standard set of APIs for inference.

Provided here is a proxy that both demonstrates the usage of these APIs and allows for easier compatibility with existing clients.

This is experimental and may not be fully API compatible, but should serve as a good starting point for exploring the Truffle while core software improves.

### Usage

```bash
truffleinferproxy --truffle truffle-5970 --host 127.0.0.1 --port 8080      

truffleinferproxy --help 
```




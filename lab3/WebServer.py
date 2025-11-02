import socket, os, urllib.parse

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind(("", 10000))
s.listen(1)
print("http://127.0.0.1:10000/index.html")
print("http://127.0.0.1:10000/myimage.jpg")
print("http://127.0.0.1:10000/myimage2.jpg")
print("http://127.0.0.1:10000/bio.html")

while True:
    c, a = s.accept()
    while True:
        data = b""
        while b"\r\n\r\n" not in data:
            chunk = c.recv(4096)
            if not chunk:
                break
            data += chunk
        if not data:
            break
        req_line = data.split(b"\r\n", 1)[0].decode()
        m, t, v = req_line.split(" ")
        path = urllib.parse.urlsplit(t).path or "/"
        if path == "/":
            path = "/index.html"
        target = os.path.join(os.getcwd(), path.lstrip("/"))
        ext = os.path.splitext(target.lower())[1]
        if ext not in (".html", ".jpg") or not os.path.isfile(target):
            body = b"<h1>404 Not Found</h1>"
            resp = (
                "HTTP/1.1 404 Not Found\r\n"
                "Content-Type: text/html\r\n"
                f"Content-Length: {len(body)}\r\n\r\n"
            ).encode() + body
            c.sendall(resp)
            continue
        with open(target, "rb") as f:
            body = f.read()
        ctype = "text/html" if ext == ".html" else "image/jpeg"
        resp = (
            "HTTP/1.1 200 OK\r\n"
            f"Content-Type: {ctype}\r\n"
            f"Content-Length: {len(body)}\r\n\r\n"
        ).encode() + body
        c.sendall(resp)

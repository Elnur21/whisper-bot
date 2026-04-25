const http = require("http");
const fs = require("fs");
const path = require("path");


// ===== CONTROLLER =====
const homeController = {
  index: (req, res) => {

    const filePath = path.join(__dirname, "index.html");

    fs.readFile(filePath, "utf-8", (err, html) => {
      if (err) {
        res.writeHead(500, { "Content-Type": "text/plain" });
        return res.end("Server Error");
      }

      res.writeHead(200, { "Content-Type": "text/html" });
      res.end(html);
    });
  }
};

// ===== ROUTER =====
function router(req, res) {
  if (req.url === "/" && req.method === "GET") {
    return homeController.index(req, res);
  }

  res.writeHead(404, { "Content-Type": "text/plain" });
  res.end("404 Not Found");
}

// ===== SERVER =====
const server = http.createServer(router);

const PORT = 3000;
server.listen(PORT, () => {
  console.log(`Server running at http://localhost:${PORT}`);
});
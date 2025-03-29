require "http/server"
require "http/headers"


HEAD = "<!DOCTYPE html>
  <html>
    <head>
      <meta charset=\"UTF-8\" />
      <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
      <meta name=\"keywords\" content=\"HTML, CSS, JavaScript\">
      <meta name=\"author\" content=\"Pierre BAZONNARD\">
      <title>Spy</title>
      <!--link rel=\"stylesheet\" href=\"spy.css\" /-->
    </head>
    <body>"

BODY = "
        <p>Platform: <span id=\"platform\"></span></p>
        <p>Vendor: <span id=\"vendor\"></span></p>
        <p>Product: <span id=\"product\"></span></p>"

FOOT = "
      <script>
        document.getElementById(\"platform\").innerHTML = navigator.platform;
        document.getElementById(\"vendor\").innerHTML   = navigator.vendor;
        document.getElementById(\"product\").innerHTML  = navigator.product;
      </script>
    </body>
  </html>"


class Appli
  include HTTP::Handler

  def call(context : HTTP::Server::Context)
    begin
      context.response.reset
      context.response.content_type = "text/html"
      headers = context.request.headers
      response = HEAD
      str = "<p>User-Agent: " + headers["User-Agent"].to_s + "</p>\n"
      response += str
      str = "<p>Host: " + headers["Host"].to_s + "</p>\n"
      response += str
      str = "<p>X-Real-IP: " + headers["X-Real-IP"].to_s + "</p>\n"
      response += str
      str = "<p>X-Forwarded-For: " + headers["X-Forwarded-for"].to_s + "</p>\n"
      response += str
      response += BODY
      response += FOOT
      context.response.puts(response)
    rescue KeyError
      call_next(context)
    end
  end

end


puts "SPY version 1.0 starting..."

# HTTP::Handler(s)
log   = HTTP::LogHandler.new
error = HTTP::ErrorHandler.new
appli = Appli.new
handlers = [ log, error, appli ]

server = HTTP::Server.new(handlers)
address = server.bind_tcp 8081
puts "Listening on http://#{address}"
puts "Use Ctrl-C to stop"
server.listen


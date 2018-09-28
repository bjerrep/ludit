
// https://stackoverflow.com/a/27220617

function ws_url(ip, port) {
	return "ws://" + ip + ":" + port;
}


function findserver(port, ipBase, ipLow, ipHigh, maxInFlight, timeout, cb) {
	var ipCurrent = +ipLow, numInFlight = 0, found = false;
    ipHigh = +ipHigh;

	console.log("scanning for websocket server")
	
    function tryOne(ip) {
        ++numInFlight;
		var ip = ipBase + ip;
		var address = ws_url(ip, port);
        var socket = new WebSocket(address);
        var timer = setTimeout(function() {
            //console.log(address + " timeout");
			var s = socket;
			socket = null;
			s.close();
			--numInFlight;
			next();

        }, timeout);
        socket.onopen = function() {
            if (socket) {
                found = true;
                console.log(address + " success");
                //clearTimeout(timer);
				socket.close();
				cb(ip, port);
				--numInFlight;
            }
        };
        socket.onerror = function(err) {
            if (socket) {
                //console.log(address + " error");
                clearTimeout(timer);
                --numInFlight;
                next();
            }
        }
    }

    function next() {
        while (ipCurrent <= ipHigh && numInFlight < maxInFlight && !found) {
            tryOne(ipCurrent++);
        }
        // if we get here and there are no requests in flight, then
        // we must be done
        if (numInFlight === 0) {
            if (!found) {
                console.log("ws not found, giving up");
                cb(null, null);
            }
        }
    }

    next();
}


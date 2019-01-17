
// https://stackoverflow.com/a/32841043

function get_local_ip() {
	window.RTCPeerConnection = window.RTCPeerConnection || window.mozRTCPeerConnection || window.webkitRTCPeerConnection;//compatibility for Firefox and chrome
	var pc = new RTCPeerConnection({iceServers:[]}), noop = function(){};      
	pc.createDataChannel('');//create a bogus data channel
	pc.createOffer(pc.setLocalDescription.bind(pc), noop);// create offer and set local description
	pc.onicecandidate = function(ice)
	{
		if (ice && ice.candidate && ice.candidate.candidate)
		{
			var myIP = /([0-9]{1,3}(\.[0-9]{1,3}){3}|[a-f0-9]{1,4}(:[a-f0-9]{1,4}){7})/.exec(ice.candidate.candidate)[1];
			console.log('local ip: ', myIP);
			pc.onicecandidate = noop;
			return myIP;
		}
	};
};

function ws_url(ip, port) {
	return "ws://" + ip + ":" + port;
}

$(".tab-list").on("click", ".tab", function(e) {
	e.preventDefault();
	
	$(".tab").removeClass("active");
	$(".tab-content").removeClass("show");
	$(this).addClass("active");
	$($(this).attr("href")).addClass("show");
	
	if ($(this).html() === "Twitse" && ws_twitse) {
		print_responsives();
		ws_twitse.send(JSON.stringify({"command": "get_history"}));
	}
});


function call_server(group, type, value) {
	console.log('new value ' + group + " " + type + " " + value);
	ludit_send({"command": "set_" + type, "group": group, "value": value.toString()});
}


/////////////////////// slider ///////////////////////

function slider_js(group, type, serial, serials, value, min, max) {

	var setter = ""
	while (serials > 0) {
		var gts = group + '_' + type + serials;
		setter += ' if ($("#slider_' + gts + '").slider("value") != ui.value) {$("#slider_' + gts + '").slider("value", ui.value);} ';
		setter += ' $(".' + gts +'").val(ui.value.toFixed(1)); ';
		--serials;
	}
	
	gts = group + '_' + type + serial;
	
	var js='$( function() {\
  	    $("#slider_' + gts + '").slider({\
  	    value:' + value + ', min: ' + min + ', max: ' + max + ', step: ' + (max - min) / 1000.0 + ',\
	    slide: function(event, ui) {\
	        call_server("' + group + '","' + type + '", ui.value);\
	        '+ setter +'\
	        return true;\
        },\
        start: function(event, ui) {\
			no_configuration_reload = true;\
		},\
		stop: function(event, ui) {\
			no_configuration_reload = false;\
			ludit_send({"command": "get_configuration", "group": "n/a"});\
		}\
    });\
    $(".' + gts + '").val( $("#slider_' + gts + '").slider("value"));\
    $(".' + gts + '").on( "slidestart", function( event, ui ) {} );\
    $(".' + gts + '").on( "slidestop", function( event, ui ) {} );\
    $(".' + gts + '").on( "slide", function( event, ui ) {} );\
	});'
	
	return js;
};

function insert_slider_html(legend, group, type, serial) {      
	var gts = group + '_' + type + serial;
	
	html = '<p><label for="amount">' + legend + ':  </label>\
	       <input type="text" class="' + gts + '" id="amount" readonly style="border:0; color:#f6931f; font-weight:bold;"></p>\
	       <div id="slider_' + gts + '" style="float:left; width:100%"></div></br>';
	
	$("#standard_" + gts).html(html);
}

function set_slider_value(group, type, serial, value) {
	var gts = group + '_' + type + serial;
	$( "." + gts ).val( parseFloat(value).toFixed(1) )
	var sldr = $("#slider_" + gts);
	sldr.slider().slider("value", value);
}

function add_slider(legend, group, type, serial, serials, value, min, max) {
	var gts = group + '_' + type + serial;
	
	if ( !document.querySelector("." + gts) )
	{
		console.log('constructing ' + gts);
		insert_slider_html(legend, group, type, serial);
		window.eval(slider_js(group, type, serial, serials, value, min, max));
		set_slider_value(group, type, value);
	} else 
	{
		while (serials > 0) {
			var gtsweep = group + '_' + type + serials;
			var current_value = document.querySelector("." + gtsweep).value;
			if (!!current_value.localeCompare(value))
			{
				set_slider_value(group, type, serials, value);
			}
			--serials;
		}
	}
}


/////////////////////// radio ///////////////////////

function insert_radio_html(group, type, serial) {      
	var gts = group + '_' + type + serial;
	var name_class = 'name="' + gts + '" class="' + gts + '" ';
    var pageid = '#page2';
	
    html = '<br><fieldset>\
            <legend>Filter order: </legend>\
            <label for="filter-2">2 \
            <input type="radio" ' + name_class + ' id="filter-2" value="2"></label>\
            <label for="filter-4">4 \
            <input type="radio" ' + name_class + ' id="filter-4" value="4"></label>\
            <label for="filter-8">8 \
            <input type="radio" ' + name_class + ' id="filter-8" value="8"></label>\
            </fieldset>';
        
    existing = $(pageid).html();
    $(pageid).html(existing + html);
}

function set_radio_value(group, type, value) {
	var serial = 1;
	var gts = group + '_' + type + serial;
    var option = document.getElementById("filter-" + value);
    option.checked = true;
}

function add_radio(group, type, serial, serials, value) {
	var gts = group + '_' + type + serial;
	console.log('constructing ' + gts);
	insert_radio_html(group, type, serial);
	set_radio_value(group, type, value);
}


/////////////////////// switch ///////////////////////

// fixit, callback doesnt work for any but the last switch on a page

function add_switch(group, ident, serial, command, ontext, offtext, is_on) {
	var key = group + "_" + ident + serial;
	$("#standard_" + key).btnSwitch({
		_group: group,
		_ident: ident,
		_command: command,
		ToggleState: is_on,
		OnValue: true,
        OffValue: false,
		OnText: ontext,
		OffText: offtext,
		OnCallback: function(val) {
			console.log(this._group + " " + this._ident + " = " + val);
			ludit_send({"command": this._command, "group": this._group, "value": val});
		},
		OffCallback: function (val) {
			console.log(this._group + " " + this._ident + " = " + val);
			ludit_send({"command": this._command, "group": this._group, "value": val});
		}
	});
}


/////////////////////// loading ///////////////////////


function insert_title_html(legend, page) {      
    var pageid = '#page' + page;
    
    html = '<h2>' + legend + '</h2>';
    
    existing = $(pageid).html();
    $(pageid).html(existing + html);
}


function insert_extended_html(group, type, serial, page) {
    var gts = 'standard_' + group + '_' + type + serial;
    var pageid = '#page' + page;

    html ='<div class="' + gts + '" id="' + gts + '"></div>'

    existing = $(pageid).html();
    $(pageid).html(existing + html);
}


// Add a node to the 'metric' treetable or update an existing one

function add_metric(root, sub, text, value) {
	var table = $("#table_metrics")
	
	var rootNode = table.treetable("node", root);
	if (!rootNode) {
		table.treetable("loadBranch", null, "<tr data-tt-id='" + root + "'><td>" + root + "</td><td></td></tr>");
		rootNode = table.treetable("node", root);
	}
	
	var subNode = table.treetable("node", sub);
	if (!subNode) {
		table.treetable("loadBranch", rootNode, "<tr data-tt-id='" + sub + "' data-tt-parent-id='" + root + "'><td>" + sub + "</td><td></td></tr>");
		subNode = table.treetable("node", sub);
	}
	
	var fqn = root + sub + text;
	var table_cell_data = text + "</td><td>" + value + "</td></tr>";
	
	var textNode = table.treetable("node", fqn);
	if (textNode) {
		// this is the outcome after mindless trashing to get a node update that appears to work.
		// See the issues https://github.com/ludo/jquery-treetable/issues/82 and https://github.com/ludo/jquery-treetable/issues/128
		// which didn't really help.
		// 
		var html = jQuery(textNode.row).html().split('</span>')[0];
		jQuery(textNode.row).html(html + "</span>" + table_cell_data);
	}
	else {
		table.treetable("loadBranch", subNode, "<tr data-tt-id='" + fqn + "' data-tt-parent-id='" + sub + "'>" + "<td>" + table_cell_data);
		table.treetable("sortBranch", subNode);
	}
}


function reload_configuration() {
    $("#page1").html('chrome mobile');
	var grps = ludit_saved_configuration['groups'];
    $("#page1").html('');
    $("#page2").html('');
    
	for (group of grps) {
        var name = group['name'];
        insert_title_html(group['legend'], 2);

		if (group['enabled']) {

            insert_title_html(group['legend'], 1);

            insert_extended_html(name, "volume", 1, 1);
            insert_extended_html(name, "volume", 2, 2);
			add_slider('Volume', name, "volume", 1, 2, group['volume'], 0.0, 100.0);
			add_slider('Volume', name, "volume", 2, 2, group['volume'], 0, 100);
            
            insert_extended_html(name, "on", 1, 1);
			add_switch(name, "on", 1, "set_on", "On", "Off", group["on"]);
            
            insert_extended_html(name, "balance", 1, 2);
			add_slider('Balance', name, "balance", 1, 1, group['balance'], -100, 100);
            
            insert_extended_html(name, "xoverfreq", 1, 2);
            add_slider('Crossover frequency', name, "xoverfreq", 1, 1, group['xoverfreq'], 300, 3000);
            
			add_radio(name, "order", 1, 1, group['xoverpoles']);
            
            insert_extended_html(name, "highlowbalance", 1, 2);
            add_slider('Low/high balance', name, "highlowbalance", 1, 1, group['highlowbalance'], -1, 1);
            
            var eq_legends = ['Band 1 : 29Hz', 'Band 2 : 59Hz', 'Band 3 : 119Hz', 'Band 4 : 237Hz', 'Band 5 : 474Hz',
                              'Band 6 : 947Hz', 'Band 7 : 1889Hz', 'Band 8 : 3770Hz', 'Band 9 : 7523Hz', 'Band 10 : 15011Hz'];
			for (const [ key, value ] of Object.entries(group['equalizer'])) {
				var gain = parseFloat(value);
                insert_extended_html(name, "band" + key, 1, 2);
				add_slider(eq_legends[parseInt(key)], name, "band" + key, 1, 1, gain, -12, 12);
			}
		}

        insert_extended_html(name, "enable", 1, 2);
        add_switch(name, "enable", 1, "set_enabled", "Enable", "Disable", group['enabled']);
	}

    for (group of grps) {
        var name = group['name'];
        if (group['enabled']) {
            set_radio_value(name, "order", group['xoverpoles']);
        }
    }
}

$(document).ready(function() {
    document.addEventListener('click',function(e) {
        elem = e.target.className.split("_");
        if (e.target && elem[1] == 'order1') {
            call_server(elem[0], "xoverpoles", e.target.value);
        }
    });
});

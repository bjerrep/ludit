
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

$('#radio_kitchen_order1').on('change', function() {
	var index = $('.kitchen_order1:checked').val();
	console.log(index);
	call_server("kitchen", "xoverpoles", index);
});

function insert_radio_html(group, type, serial) {      
	var gts = group + '_' + type + serial;
	
	var name_class = 'name="' + gts + '" class="' + gts + '" ';
	
html = '<fieldset>\
<legend>Filter order: </legend>\
<label for="filter-1">2 \
<input type="radio" ' + name_class + ' id="filter-1" value="2"></label>\
<label for="filter-2">4 \
<input type="radio" ' + name_class + ' id="filter-2" value="4"></label>\
<label for="filter-3">8 \
<input type="radio" ' + name_class + ' id="filter-3" value="8"></label>\
</fieldset>';
	
	document.getElementById("radio_" + gts).innerHTML = html;
}

function set_radio_value(group, type, value) {
	var serial = 1;
	var gts = group + '_' + type + serial;
	$('.kitchen_order1').filter('[value=' + value + ']').prop('checked', true);
}

function add_radio(group, type, serial, serials, value) {
	var gts = group + '_' + type + serial;
	console.log('constructing ' + gts);
	insert_radio_html(group, type, serial);
	set_radio_value(group, type, value);
}


/////////////////////// switch ///////////////////////

function add_switch(group, ident, serial, is_on) {
	var key = "switch_" + group + "_" + ident + serial;
	$("#" + key).btnSwitch({
		_group: group,
		_ident: ident,
		ToggleState: is_on,
		OnValue: true,
		OnCallback: function(val) {
			console.log(this._group + " " + this._ident + " = " + val);
			ludit_send({"command": "set_on", "group": this._group, "value": val});
		},
		OffValue: false,
		OffCallback: function (val) {
			//val = val.toString();
			console.log(this._group + " " + this._ident + " = " + val);
			ludit_send({"command": "set_on", "group": this._group, "value": val});
		}
	});
}


/////////////////////// loading ///////////////////////

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
	var grps = ludit_saved_configuration['groups'];
	
	for (group of grps) {
		if (group['enabled']) {
			var name = group['name'];
			add_slider('Volume', name, "volume", 1, 2, group['volume'], 0.0, 100.0);
			add_slider('Volume', name, "volume", 2, 2, group['volume'], 0, 100);
			add_switch(name, "on", 1, group["on"]);
			add_slider('Balance', name, "balance", 1, 1, group['balance'], -100, 100);
			add_slider('Crossover frequency', name, "xoverfreq", 1, 1, group['xoverfreq'], 300, 3000);
			add_radio(name, "order", 1, 1, group['xoverpoles']);
			add_slider('Low/high balance', name, "highlowbalance", 1, 1, group['highlowbalance'], -1, 1);
			var eq_legends = ['Band 0 : 29Hz', 'Band 1 : 59Hz'];
			for (const [ key, value ] of Object.entries(group['equalizer'])) {
				var gain = parseFloat(value);
				add_slider(eq_legends[parseInt(key)], name, "band" + key, 1, 1, gain, -12, 12);
			}
		}
	}
}


$(document).ready(function() {

});


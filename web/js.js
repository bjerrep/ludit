
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


$( function() {
	$("#slider_kitchen_crossover").slider({
		value:1000, min: 300, max: 3000, step: 10,
		slide: function(event, ui) {
			$("#crossover_label").val(ui.value);
			ludit_send({"command": "crossover", "frequency": ui.value.toString(), "group": "kitchen"});
			//console.log(ui.value);
		}
	});
	$("#crossover_label").val( $("#slider_kitchen_crossover").slider("value") );
});


$( function() {
	$("#slider_stereo").slider({
		value:100, min: 0, max: 100, step: 1,
		slide: function( event, ui ) {
			$( "#stereo_value" ).val( ui.value );
			ludit_send({"command": "volume", "volume": ui.value.toString(), "group": "stereo"});
			console.log(ui.value);
		}
	});
	$( "#stereo_value" ).val( $( "#slider_stereo" ).slider( "value" ) );

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
		setter += ' $(".' + gts +'").val(ui.value); ';
		--serials;
	}
	
	gts = group + '_' + type + serial;
	
	var js='$( function() {\
  	    $("#slider_' + gts + '").slider({\
	    value:' + value + ', min: ' + min + ', max: ' + max + ', step: ' + (max - min) / 1000.0 + ',\
	    slide: function(event, ui) {\
	        ' + setter + ' \
	        call_server("' + group + '","' + type + '", ui.value);\
        }\
    });\
    $(".' + gts + '").val( $("#slider_' + gts + '").slider("value"));\
});'

//console.log('js=' + js)

return js;
};

function insert_slider_html(legend, group, type, serial) {      
	var gts = group + '_' + type + serial;
	
	html = '<p><label for="amount">' + legend + ':  </label>\
	       <input type="text" class="' + gts + '" id="amount" readonly style="border:0; color:#f6931f; font-weight:bold;"></p>\
	       <div id="slider_' + gts + '" style="float:left; width:100%"></div></br>';
	
	document.getElementById("standard_" + gts).innerHTML = html;
}

function set_slider_value(group, type, value) {
	var serial = 1;
	var gts = group + '_' + type + serial;
	$( "." + gts ).val( value )
	$("#slider_" + gts).slider("value", value);
}

function add_slider(legend, group, type, serial, serials, value, min, max) {
	var gts = group + '_' + type + serial;
	console.log('constructing ' + gts);
	insert_slider_html(legend, group, type, serial);
	window.eval(slider_js(group, type, serial, serials, value, min, max));
	set_slider_value(group, type, value);
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

function insert_switch_html(label, group, ident, serial) {      
	var gts = group + '_' + ident + serial;
	
	var name_class = 'name="m_switch_' + gts + '" class="m_switch_' + gts + '" ';
	
	html = '<div class="m_setting_container"><div class="m_setting_area"><div class="m_setting_section"><div class="m_settings_item"><div class="m_settings_row"><div class="m_settings_table">\
	<div class="m_settings_cell m_settings_label"></div>\
	<div class="m_settings_cell">\
	<input type="checkbox" id="switcher" ' + name_class + ' value="0" entity="' + label + '">\
	</div>\
	</div></div></div></div></div></div>';
	
	console.log(html);
	
	document.getElementById("m_switch_" + gts).innerHTML = html;
}

function add_switch(label, group, ident, serial) {
	//insert_switch_html(label, group, ident, serial);
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
			add_slider('Volume', name, "volume", 1, 2, group['volume'], 0, 100);
			add_slider('Volume', name, "volume", 2, 2, group['volume'], 0, 100);
			add_slider('Balance', name, "balance", 1, 1, group['balance'], -100, 100);
			add_slider('Crossover frequency', name, "xoverfreq", 1, 1, group['xoverfreq'], 300, 3000);
			add_radio(name, "order", 1, 1, group['xoverpoles']);
			add_slider('Low/high balance', name, "highlowbalance", 1, 1, group['highlowbalance'], -1, 1);
			var eq_legends = ['Band 0 : 29Hz', 'Band 1 : 59Hz'];
			for (const [ key, value ] of Object.entries(group['equalizer'])) {
				var gain = parseFloat(value);
				add_slider(eq_legends[parseInt(key)], name, "band" + key, 1, 1, gain, -12, 12);
			}
			add_switch('Play', name, "active", 1, 1);
		}
	}
}

$(document).ready(function() {
	
	
	$(".m_switch_check:checkbox").mSwitch({
		onRender:function(elem){
			var entity = elem.attr("entity");
			var label = elem.parent().parent().prev(".m_settings_label");
			if (elem.val() == 0) {
				$.mSwitch.turnOff(elem);
				label.html("<span class=\"m_red\">Off</font>");
			} else {
				label.html("<span class=\"m_green\">On</font>");
				$.mSwitch.turnOn(elem);
			}
		},
		onRendered:function(elem){
			console.log(elem);
		},
		onTurnOn:function(elem){
			var entity = elem.attr("entity");
			var label = elem.parent().parent().prev(".m_settings_label");
			if (elem.val() == "0") {
				elem.val("1");
				label.html("<span class=\"m_green\">On</font>");
			} else {
				label.html("<span class=\"m_red\">Off</font>");
			}
		},
		onTurnOff:function(elem){
			var entity = elem.attr("entity");
			var label = elem.parent().parent().prev(".m_settings_label");
			if (elem.val() == 1) {
				elem.val("0");
				label.html("<span class=\"m_red\">Off</font>");
			} else {
				label.html("<span class=\"m_green\">On</font>");
			}
		}
	});
	
});


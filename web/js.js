
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


var pending_key = null;
var pending_command = null;

function flush_pending() {
	ludit_send(pending_command);
	pending_key = null;
}

function call_server(groupname, index, type, value) {
    pending_command = {"command": "setparam",
                        "name": groupname,
                        "param": { [index]: { [type]: value.toString() }}};
	if (!pending_key) {
        pending_key = type + group;
        setTimeout(flush_pending, 100);
    }
}


/////////////////////// slider ///////////////////////

function slider_log(message) {
    console.log("slider: " + message);
};

function slider_js(groupname, index, type, serial, serials, value, min, max, decimals) {

	var setter = ""
	while (serials > 0) {
		let gts = groupname + '_' +  index + '_' + type + '_' + serials;
		setter += ' if ($("#slider_' + gts + '").slider("value") != ui.value) {$("#slider_' + gts + '").slider("value", ui.value); ';
		setter += ' $(".' + gts +'").val(ui.value.toFixed('+decimals+')); } ';
		--serials;
	}

	let gts = groupname + '_' +  index + '_' + type + '_' + serial;

	var js='$( function() {\
  	    $("#slider_' + gts + '").slider({\
  	    value:' + value + ', min: ' + min + ', max: ' + max + ', step: ' + (max - min) / 1000.0 + ',\
	    slide: function(event, ui) {\
	        call_server("' + groupname + '", "' + index + '", "' + type + '", ui.value);\
	        '+ setter +'\
	        return true;\
        },\
        start: function(event, ui) {\
			no_configuration_reload = true;\
		},\
		stop: function(event, ui) {\
			no_configuration_reload = false;\
		}\
    });\
    $(".' + gts + '").val( $("#slider_' + gts + '").slider("value").toFixed('+decimals+') );\
    $(".' + gts + '").on( "slidestart", function( event, ui ) {} );\
    $(".' + gts + '").on( "slidestop", function( event, ui ) {} );\
    $(".' + gts + '").on( "slide", function( event, ui ) {} );\
	});'

	return js;
};


function insert_slider_html(legend, groupname, index, type, serial) {
	let gts = groupname + '_' +  index + '_' + type + '_' + serial;

	html = '<p><label for="amount">' + legend + ':  </label>\
	       <input type="text" class="' + gts + '" id="' + gts + 'amount" readonly style="border:0; color:#f6931f; font-weight:bold;"></p>\
	       <div id="slider_' + gts + '" style="float:left; width:100%"></div></br>';

	$("#standard_" + gts).html(html);
}


function add_slider(legend, groupname, index, type, serial, serials, group_or_value, min, max) {
	let gts = groupname + '_' + index + '_' + type + '_' + serial;
	let value = 0;
	if (isNaN(group_or_value))
	    value = group_or_value[index][type];
	else
	    value = group_or_value;

    let span = max - min;
    let decimals = 0;
    if (span < 10.0) {
        decimals = 2;
    }
    else if (span < 100.0) {
        decimals = 1;
    }

	if ( !document.querySelector("." + gts) ) {
		insert_slider_html(legend, groupname, index, type, serial, decimals);
		window.eval(slider_js(groupname, index, type, serial, serials, value, min, max, decimals));
	}
}


/////////////////////// radio ///////////////////////

function add_radio(group, groupname, index, type, serial, page) {
    let gts = groupname + '_' +  index + '_' + type + '_' + serial;

html =
    '<br><form><fieldset><legend class="legend1">Filter order: </legend>\
    <input type="radio" class="'+gts+'" name="poles" value=2 id="filter-2"><label for="filter-2"> 2</label>\
    <input type="radio" class="'+gts+'" name="poles" value=4 id="filter-4"><label for="filter-4"> 4</label>\
    <input type="radio" class="'+gts+'" name="poles" value=8 id="filter-8"><label for="filter-8"> 8</label>\
    </fieldset></form>';

    var pageid = '#page' + page;
    existing = $(pageid).html();
    $(pageid).html(existing + html);
}

function set_radio_value(groupname, index, type, serial, value) {
	let gts = groupname + '_' +  index + '_' + type + '_' + serial;
	$("input[class=" + gts + "][value=" + value + "]").prop('checked', true);
}

/////////////////////// switch ///////////////////////

function add_switch(group, groupname, index, type, serial, page, label, bold) {
	var gts = groupname + '_' +  index + '_' + type + '_' + serial;

    let is_on = group[index][type] == "true";
    let checked = is_on ? "checked" : "unchecked";
    let txt = bold ? '<b>' + label + '</b>' : label;

    html ='<input type="checkbox" name="' + gts + '" class="checkbox" id="' + gts +
          '" ' + checked + '><label for="' + gts + '">&#160;&#160;' + txt + '</label>'

    var pageid = '#page' + page;
    existing = $(pageid).html();
    $(pageid).html(existing + html);
}

/////////////////////// loading ///////////////////////


function insert_title_html(legend, page) {
    var pageid = '#page' + page;

    html = '<h2>' + legend + '</h2>';

    existing = $(pageid).html();
    $(pageid).html(existing + html);
}


function insert_extended_html(group, index, type, serial, page) {
    var gts = 'standard_' + group + '_' + index + '_' + type + '_' + serial;
    var pageid = '#page' + page;

    html ='<div class="' + gts + '" id="' + gts + '"></div>'

    existing = $(pageid).html();
    $(pageid).html(existing + html);
}


// Add a node to the 'metric' treetable or update an existing one

function add_node(root, sub, text, value, table) {

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

function add_metric(root, sub, text, value) {
    add_node(root, sub, text, value, $("#table_metrics"));
}
    
function add_twitse_metric(root, sub, text, value) {
    add_node(root, sub, text, value, $("#twitse_table_metrics"));
}

function reload_configuration() {
	var grps = ludit_saved_configuration['groups'];
    $("#page1").html('');
    $("#page2").html('');

    has_enabled_groups = false;

	for (group of grps) {
	    let general = group['general']
        let groupname = general['name'];
        let legend = general['legend']
        insert_title_html(legend, 2);

		if (general['enabled'] == "true") {
            has_enabled_groups = true;
            insert_title_html(general['legend'], 1);

            insert_extended_html(groupname, "levels", "volume", 1, 1);
            insert_extended_html(groupname, "levels", "volume", 2, 2);
			add_slider('Volume', groupname, "levels", "volume", 1, 2, group, 0.0, 100.0);
			add_slider('Volume', groupname, "levels", "volume", 2, 2, group, 0, 100);

            insert_extended_html(groupname, "general", "playing", 1, 1);
			add_switch(group, groupname, "general", "playing", 1, 1, "Playing", true);

            insert_extended_html(groupname, "levels", "balance", 1, 2);
			add_slider('Balance', groupname, "levels", "balance", 1, 1, group, -100, 100);

            if (group['stereoenhance']['visible'] == 'true') {
			    insert_extended_html(groupname, "stereoenhance", "depth", 1, 2);
			    add_slider('Stereo enhance', groupname, "stereoenhance", "depth", 1, 1, group, 0, 1);
			    add_switch(group, groupname, "stereoenhance", "enabled", 1, 2, "Stereo enhance enabled", false);
			}

            insert_extended_html(groupname, "xover", "freq", 1, 2);
            add_slider('Crossover frequency', groupname, "xover", "freq", 1, 1, group, 300, 3000);

			add_radio(group, groupname, "xover", "poles", 1, 2);

            insert_extended_html(groupname, "xover", "highlowbalance", 1, 2);
            add_slider('Low/high balance', groupname, "xover", "highlowbalance", 1, 1, group, -1, 1);

            var eq_legends = ['Band 1 : 29Hz', 'Band 2 : 59Hz', 'Band 3 : 119Hz', 'Band 4 : 237Hz', 'Band 5 : 474Hz',
                              'Band 6 : 947Hz', 'Band 7 : 1889Hz', 'Band 8 : 3770Hz', 'Band 9 : 7523Hz', 'Band 10 : 15011Hz'];
			for (const [ key, value ] of Object.entries(group["levels"]['equalizer'])) {
				var gain = parseFloat(value);
                insert_extended_html(groupname, "levelsequalizer", key, 1, 2);
				add_slider(eq_legends[parseInt(key)], groupname, "levelsequalizer", key, 1, 1, gain, -12, 12);
			}
		}

        add_switch(group, groupname, "general", "enabled", 1, 2, legend + " enabled", true);

        $("#page1").html($("#page1").html() + '<br>');
        $("#page2").html($("#page2").html() + '<br>');
	}

    if (!has_enabled_groups) {
        $("#page1").html('No groups are enabled....');
    }

    for (group of grps) {
        if (group['general']['enabled'] == 'true') {
            var groupname = group['general']['name'];
            set_radio_value(groupname, 'xover', 'poles', 1, group['xover']['poles']);
        }
    }
}


$(document).ready(function() {
    document.addEventListener('click',function(e) {
        if (e.target) {
            if (e.target.name == "poles")
            {
                elem = e.target.className.split("_");
                let groupname = elem[0];
                let index = elem[1];
                let type = elem[2];
                order = e.target.id.split("-");

                call_server(groupname, index, type, order[1]);
            }
            else if (e.target.className == "checkbox"){
                let elem = e.target.name.split("_");
                let groupname = elem[0];
                let index = elem[1];
                let type = elem[2];

                call_server(groupname, index, type, e.target.checked ? "true" : "false");
            }
        }
    });
});

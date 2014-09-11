function depthFirstSearch(node) {
	if (typeof node.children != "undefined") {
		for (var i=0, c=node.children.length; i<c; i++) {
			depthFirstSearch(node.children[i]);
		}
	}
}

function gatherTips(node, tips) {
	if (typeof node.children != "undefined") {
		for (var i=0, c=node.children.length; i<c; i++) {
			gatherTips(node.children[i], tips);
		}
	}
	else {
		tips.push(node);
	}
	return tips;
}

function gatherInternals(node, internals) {
	if (typeof node.children != "undefined") {
		internals.push(node);
		for (var i=0, c=node.children.length; i<c; i++) {
			gatherInternals(node.children[i], internals);
		}
	}
	return internals;
}

function setFrequencies(node) {
	if (typeof node.frequency == "undefined") {
		node.frequency = 0.01;
	}
	if (typeof node.children != "undefined") {
		for (var i=0, c=node.children.length; i<c; i++) {
			setFrequencies(node.children[i]);
		}
	}
}

/*
function setFrequencies(node, date) {
	if (typeof node.frequencies != "undefined") {
		var sdate = ymd_format(date);
		var dates = [];
		for (var i=0, c=node.frequencies.length; i<c; i++) {
			dates.push(node.frequencies[i].date);
		}
		var index = d3.bisect(dates, sdate) - 1;
		node.frequency = node.frequencies[index].frequency;
	}
	if (typeof node.children != "undefined") {
		for (var i=0, c=node.children.length; i<c; i++) {
			setFrequencies(node.children[i], date);
		}
	}	
}
*/

function minimumAttribute(node, attr, min) {
	if (typeof node.children != "undefined") {
		for (var i=0, c=node.children.length; i<c; i++) {
			min = minimumAttribute(node.children[i], attr, min);
		}
	}
	else {
		if (node[attr] < min) {
			min = node[attr];
		}
	}
	return min;
}

function maximumAttribute(node, attr, max) {
	if (typeof node.children != "undefined") {
		for (var i=0, c=node.children.length; i<c; i++) {
			max = maximumAttribute(node.children[i], attr, max);
		}
	}
	else {
		if (node[attr] > max) {
			max = node[attr];
		}
	}
	return max;
}

var width = 800,
	height = 600;
	
var globalDate = new Date();
var ymd_format = d3.time.format("%Y-%m-%d");		

var tree = d3.layout.tree()
	.size([height, width]);

var treeplot = d3.select("#treeplot")
	.attr("width", width)
	.attr("height", height);
		
var tooltip = d3.tip()
	.direction('e')
	.attr('class', 'd3-tip')
	.offset([0, 10])
	.html(function(d) {
		string = ""
		if (typeof d.frequency != "undefined") {
			if (d.frequency > 0.01) {
				string = d.frequency;
			}
		}
		if (typeof d.target != "undefined") {
			if (typeof d.target.frequency != "undefined") {
				if (d.target.frequency > 0.01) {
					string = d.target.frequency;
				}
			}	
		}	
		if (typeof d.strain != "undefined") {
			string = d.strain;
		}		
		return string;
	});
	
treeplot.call(tooltip);		

function rescale(dMin, dMax, lMin, lMax, xScale, yScale, nodes, links, tips, internals) {

	var speed = 1500;
	xScale.domain([dMin,dMax]);
	yScale.domain([lMin,lMax]);
	
	nodes.forEach(function (d) {
		d.x = xScale(d.xvalue);
		d.y = yScale(d.yvalue);			 
	});	
		
	treeplot.selectAll(".tip").data(tips)
    	.transition().duration(speed)
    	.attr("cx", function(d) { return d.x; })
    	.attr("cy", function(d) { return d.y; }); 
    	
	treeplot.selectAll(".internal").data(internals)
    	.transition().duration(speed)
		.attr("x", function(d) { 
			if (typeof d.frequency != "undefined") {		
				return d.x - 5*Math.sqrt(d.frequency) - 0.5;
			}
			else {
				return d.x - 1;
			}			
		})
		.attr("y", function(d) { 
			if (typeof d.frequency != "undefined") {		
				return d.y - 5*Math.sqrt(d.frequency) - 0.5;
			}
			else {
				return d.y - 1;
			}			
		});  
	    
	treeplot.selectAll(".link").data(links)
    	.transition().duration(speed)
		.attr("points", function(d) {
			var mod = 5*Math.sqrt(d.target.frequency)+0.5;
			return (d.source.x-mod).toString() + "," + d.source.y.toString() + " " 
			+ (d.source.x-mod).toString() + "," + d.target.y.toString() + " "
			+ (d.target.x).toString() + "," + d.target.y.toString()
		});	   		
		
}

d3.json("https://s3.amazonaws.com/augur-data/data/auspice.json", function(error, root) {
//d3.json("auspice.json", function(error, root) {
	var nodes = tree.nodes(root),
		links = tree.links(nodes);
	
	var rootNode = nodes[0];
	var tips = gatherTips(rootNode, []);
	var internals = gatherInternals(rootNode, []);
	setFrequencies(rootNode);
		
	var	xValues = nodes.map(function(d) {
  		return +d.xvalue;
  	});  
  	
	var yValues = nodes.map(function(d) {
  		return +d.yvalue;
  	}); 
  	
  	var dateValues = nodes.filter(function(d) {
		return typeof d.date === 'string';
  		}).map(function(d) {
  		return new Date(d.date);
  	}); 	
  	
  	var yearValues = nodes.filter(function(d) {
		return typeof d.date === 'string';
  		}).map(function(d) {
  		return (new Date(d.date)).getFullYear();
  	}); 	  	

	var xScale = d3.scale.linear()
		.domain([d3.min(xValues), d3.max(xValues)])
		.range([10, width-10]);
		
	var yScale = d3.scale.linear()
		.domain([d3.min(yValues), d3.max(yValues)])
		.range([10, height-10]);	
						
	var dateScale = d3.time.scale()
		.domain([new Date(d3.min(dateValues) + 30), new Date()])
		.range([-100, 100])
		.clamp([true]);
		
	var yearScale = d3.scale.ordinal()
		.domain([2014, "undefined", 2011, 2012, 2013])
		.range(["#ff7f0e", "#1f77b4", "#7f7f7f", "#7f7f7f", "#7f7f7f"]);
		
	var recencyColorScale = d3.scale.threshold()
		.domain([0.00, 0.33, 0.66, 1.0])
		.range(["#aaa", "#E04328", "#E78C36", "#CFB642", "#799CB3"]);	// red, orange, yellow, blue
		
	var recencySizeScale = d3.scale.threshold()
		.domain([0.00, 0.33, 0.66, 1.0])
		.range([0, 3.25, 2.5, 1.75, 1]);				
		
	var freqScale = d3.scale.sqrt()
		.domain([0, 1])
		.range([1, 10]);
							
	nodes.forEach(function (d) {
		d.x = xScale(d.xvalue);
		d.y = yScale(d.yvalue);			 
	});

	// straight links
/*	var link = treeplot.selectAll(".link")
		.data(links)
		.enter().append("line")
		.attr("class", "link")
		.attr("x1", function(d) { return d.source.x; })
	    .attr("y1", function(d) { return d.source.y; })
	    .attr("x2", function(d) { return d.target.x; })
	    .attr("y2", function(d) { return d.target.y; }); 
  */	    	    
	var link = treeplot.selectAll(".link")
		.data(links)
		.enter().append("polyline")
		.attr("class", "link")
		.attr("points", function(d) {
			var mod = 5*Math.sqrt(d.target.frequency)+0.5;
			return (d.source.x-mod).toString() + "," + d.source.y.toString() + " " 
			+ (d.source.x-mod).toString() + "," + d.target.y.toString() + " "
			+ (d.target.x).toString() + "," + d.target.y.toString()
		})
	    .style("stroke-width", function(d) {
			return freqScale(d.target.frequency);		    	
	    })
		.on('mouseover', tooltip.show)
      	.on('mouseout', tooltip.hide)	    
     	.on('click', function(d) { 
      		var dMin = minimumAttribute(d.target, "xvalue", d.target.xvalue),
      			dMax = maximumAttribute(d.target, "xvalue", d.target.xvalue),
      			lMin = minimumAttribute(d.target, "yvalue", d.target.yvalue),
      			lMax = maximumAttribute(d.target, "yvalue", d.target.yvalue);
      		rescale(dMin, dMax, lMin, lMax, xScale, yScale, nodes, links, tips, internals)
      	});   	  
      	
	tips.forEach(function (d) {
		var date = new Date(d.date);		
		var oneYear = 365.25*24*60*60*1000; // days*hours*minutes*seconds*milliseconds
		var diffYears = (globalDate.getTime() - date.getTime()) / oneYear;		
		d.diff = diffYears; 
	});	
	    
	var tipCircles = treeplot.selectAll(".tip")
		.data(tips)
		.enter()
		.append("circle")
		.attr("class", "tip")
		.attr("cx", function(d) {return d.x})
		.attr("cy", function(d) {return d.y})
		.attr("r", function(d) { 
			return recencySizeScale(d.diff);
		})			
		.style("fill", function(d) { 
			var col = recencyColorScale(d.diff);
			return d3.rgb(col).brighter([0.7]).toString();	
		})	
		.style("stroke", function(d) { 
			var col = recencyColorScale(d.diff);
			return d3.rgb(col).toString();	
		})					
		.on('mouseover', tooltip.show)
      	.on('mouseout', tooltip.hide);
      	      	
	var drag = d3.behavior.drag()
		.origin(function(d) { return d; })
		.on("drag", dragged);    	
	
	function dragged(d) {
		
		d.date = dateScale.invert(d3.event.x);
		d.x = dateScale(d.date);
		d3.selectAll(".counter-text")
			.text(function(d){ 
    			return format(d.date) 
    		});
		globalDate = d.date;
		tips.forEach(function (d) {
			var date = new Date(d.date);		
			var oneYear = 365.25*24*60*60*1000; // days*hours*minutes*seconds*milliseconds
			var diffYears = (globalDate.getTime() - date.getTime()) / oneYear;		
			d.diff = diffYears; 
		});			
		d3.selectAll(".tip")
			.attr("r", function(d) { 
				return recencySizeScale(d.diff);
			})			
			.style("fill", function(d) { 
				var col = recencyColorScale(d.diff);
				return d3.rgb(col).brighter([0.7]).toString();	
			})	    		
			.style("stroke", function(d) { 
				var col = recencyColorScale(d.diff);
				return d3.rgb(col).toString();	
			}); 		
		
	}
		
	var counterData = {}
	counterData['date'] = globalDate	
	counterData['x'] = dateScale(globalDate)
			    	
	var format = d3.time.format("%Y %b %-d");
	var counterText = treeplot.selectAll(".counter-text")
		.data([counterData])
		.enter()
		.append("text")			
		.attr("class", "counter-text") 
    	.attr("transform", "translate(100,40)")
    	.style("text-anchor", "middle")
    	.style("alignment-baseline", "middle")
    	.text(function(d){ 
    		return format(d.date) 
    	})
    	.call(drag);     
    	  	
	d3.select("#reset")
        .on("click", function(d) {
			var dMin = d3.min(xValues),
      			dMax = d3.max(xValues),
      			lMin = d3.min(yValues),
      			lMax = d3.max(yValues);        	
            rescale(dMin, dMax, lMin, lMax, xScale, yScale, nodes, links, tips, internals);
		})  
		
});

# estimates clade frequencies using SMC
from scipy.interpolate import interp1d
import time
from io_util import *
from tree_util import *
from seq_util import *
from date_util import *
import numpy as np

debug = False

cols  = np.array([(166,206,227),(31,120,180),(178,223,138),(51,160,44),(251,154,153),(227,26,28),(253,191,111),(255,127,0),(202,178,214),(106,61,154)], dtype=float)/255
def running_average(obs, ws):
	'''
	calculates a running average
	obs 	--	observations
	ws 		--	winodw size (number of points to average)
	'''
	try:
		tmp_vals = np.convolve(np.ones(ws, dtype=float)/ws, obs, mode='same')
		# fix the edges. using mode='same' assumes zeros outside the range
		if ws%2==0:
			tmp_vals[:ws//2]*=float(ws)/np.arange(ws//2,ws)
			if ws//2>1:
				tmp_vals[-ws//2+1:]*=float(ws)/np.arange(ws-1,ws//2,-1.0)
		else:
			tmp_vals[:ws//2]*=float(ws)/np.arange(ws//2+1,ws)
			tmp_vals[-ws//2:]*=float(ws)/np.arange(ws,ws//2,-1.0)			
	except:
		import pdb; pdb.set_trace()
	return tmp_vals

def fix_freq(freq, pc):
	'''
	restricts frequencies to the interval [pc, 1-pc]
	'''
	freq[np.isnan(freq)]=pc
	return np.minimum(1-pc, np.maximum(pc,freq))

def get_pivots(start=None, stop=None, pivots_per_year=6):
	return np.arange(np.floor(time_interval[0]*pivots_per_year), np.ceil(time_interval[1]*pivots_per_year)+0.5, 1.0)/pivots_per_year

def get_extrapolation_pivots(start=None, dt=0.5):
	return np.arange(np.floor(time_interval[1]*pivots_per_year), np.ceil((dt+time_interval[1])*pivots_per_year)+0.5, 1.0)/pivots_per_year


def logit_transform(freq):
	return np.log(freq/np.maximum(1e-10,(1-freq)))

def logit_inv(logit_freq):
	logit_freq[logit_freq<-20]=-20
	logit_freq[logit_freq>20]=20
	tmp_freq = np.exp(logit_freq)
	return tmp_freq/(1.0+tmp_freq)

def pq(p):
	return p*(1-p)

def logit_regularizer(logit_freqs):
	return reg*np.mean(np.abs(8-np.abs(logit_freqs))) # penalize too large or too small pivots

def extrapolation(freq_interp,x):
	def ep(freq_interp, x):
		if x>freq_interp.x[-1]:
			return freq_interp.y[-1] + (freq_interp.y[-1] - freq_interp.y[-2])/(freq_interp.x[-1] - freq_interp.x[-2]) * (x-freq_interp.x[-1])
		elif x<freq_interp.x[0]:
			return freq_interp.y[0] + (freq_interp.y[1] - freq_interp.y[0])/(freq_interp.x[1] - freq_interp.x[0]) * (x-freq_interp.x[0])
		else:
			return float(freq_interp(x))

	if np.isscalar(x): 
		return ep(freq_interp,x)
	else:
		return np.array([ep(freq_interp,tmp_x) for tmp_x in x])

class frequency_estimator(object):
	'''
	estimates a smooth frequency trajectory given a series of time stamped
	0/1 observations. The most likely set of frequencies at specified pivot values
	is deterimned by numerical minimization. Likelihood consist of a bernoulli sampling
	term as well as a term penalizing rapid frequency shifts. this term is motivated by 
	genetic drift, i.e., sampling variation.
	'''

	def __init__(self, observations, pivots = None, stiffness = 20.0, inertia = 0.0, logit=False, verbose = 0):
		self.tps = np.array([x[0] for x in observations])
		self.obs = np.array([x[1]>0 for x in observations])
		self.stiffness = stiffness
		self.inertia = inertia
		self.interpolation_type = 'linear'
		self.logit = logit
		self.verbose=verbose
		# make sure they are searchsorted
		tmp = np.argsort(self.tps)
		self.full_tps = self.tps[tmp]
		self.full_obs = self.obs[tmp]

		if pivots is None:
			self.final_pivot_tps = get_pivots(self.tps[0], self.tps[-1])
		elif np.isscalar(pivots):
			self.final_pivot_tps = np.linspace(self.tps[0], self.tps[-1], pivots)
		else:
			self.final_pivot_tps = pivots

	def initial_guess(self, pivots, ws=50):
		# generate a useful initital case from a running average of the counts
		tmp_vals = running_average(self.obs, ws)
		tmp_interpolator = interp1d(self.tps, tmp_vals, bounds_error=False, fill_value = -1)
		pivot_freq = tmp_interpolator(pivots)
		pivot_freq[pivots<=tmp_interpolator.x[0]] = tmp_vals[0]
		pivot_freq[pivots>=tmp_interpolator.x[-1]] = tmp_vals[-1]
		pivot_freq = fix_freq(pivot_freq, pc)
		if self.logit:
			self.pivot_freq = logit_transform(pivot_freq)

		return pivot_freq


	def stiffLH(self, pivots):
		if self.logit: # if logit, convert to frequencies
			freq = logit_inv(pivots)
		else:
			freq = pivots
		dfreq = np.diff(freq)
		dt = np.diff(self.pivot_tps)
		tmp_freq = fix_freq(freq,dfreq_pc)
		# return wright fisher diffusion likelihood for frequency change. 
		# return -0.25*self.stiffness*np.sum(dfreq**2/np.diff(self.pivot_tps)/pq(fix_freq(freq[:-1],dfreq_pc)))
		return -0.25*self.stiffness*(np.sum((dfreq[1:] - self.inertia*dfreq[:-1])**2/(dt[1:]*pq(tmp_freq[1:-1])))
									+dfreq[0]**2/(dt[0]*pq(tmp_freq[0])))


	def logLH(self, pivots):
		freq = interp1d(self.pivot_tps, pivots, kind=self.interolation_type)
		if self.logit: # if logit, convert to frequencies
			estfreq = fix_freq(logit_inv(freq(self.tps)), pc)
		else:
			estfreq = fix_freq(freq(self.tps), pc)
		stiffness_LH = self.stiffLH(pivots)
		bernoulli_LH = np.sum(np.log(estfreq[self.obs])) + np.sum(np.log((1-estfreq[~self.obs])))
		LH = stiffness_LH + bernoulli_LH 
		if self.verbose>2: print "LH:",bernoulli_LH,stiffness_LH
		if self.logit:
			return -LH/len(self.obs) + logit_regularizer(pivots)
		else:
			return -LH/len(self.obs)+100000*(np.sum((pivots<0)*np.abs(pivots))+np.sum((pivots>1)*np.abs(pivots-1)))


	def learn(self):
		from scipy.optimize import fmin_powell as minimizer
		switches = np.abs(np.diff(self.obs)).nonzero()[0]
		try:
			if len(switches)>5:
				first_switch = self.tps[switches[0]]
				last_switch = self.tps[switches[-1]]
			else:
				first_switch = self.tps[0]
				last_switch = self.tps[-1]
			if first_switch>self.final_pivot_tps[0] and first_switch < self.final_pivot_tps[-1]:
				first_pivot = max(0, np.where(first_switch<=self.final_pivot_tps)[0][0] - extra_pivots)
			else:
				first_pivot=0
			if last_switch<self.final_pivot_tps[-1] and last_switch>self.final_pivot_tps[0]:
				last_pivot = min(len(self.final_pivot_tps), np.where(last_switch>self.final_pivot_tps)[0][-1]+extra_pivots)
			else:
				last_pivot = len(self.final_pivot_tps)
			tmp_pivots = self.final_pivot_tps[first_pivot:last_pivot]
			if min(np.diff(tmp_pivots))<0.000001:
				print pivots
			self.tps = self.full_tps[(self.full_tps>=tmp_pivots[0])*(self.full_tps<tmp_pivots[-1])]
			self.obs = self.full_obs[(self.full_tps>=tmp_pivots[0])*(self.full_tps<tmp_pivots[-1])]
		except:
			import pdb; pdb.set_trace()

		self.pivot_freq = self.initial_guess(tmp_pivots, ws=2*(min(50,len(self.obs))//2))
		self.frequency_estimate = interp1d(tmp_pivots, self.pivot_freq, kind=self.interolation_type, bounds_error=False)
		if self.verbose:
			print "Initial pivots:", tmp_pivots
		steps= [4,2,1]
		for step in steps:
			# subset the pivots, if the last point is not included, attach it
			self.pivot_tps = tmp_pivots[::step]
			if self.pivot_tps[-1]!=tmp_pivots[-1]:
				self.pivot_tps = np.concatenate((self.pivot_tps, tmp_pivots[-1:]))

			self.pivot_freq = self.frequency_estimate(self.pivot_tps)

			# determine the optimal pivot freqquencies
			self.pivot_freq = minimizer(self.logLH, self.pivot_freq, ftol = tol, xtol = tol, disp = self.verbose>0)
			# instantiate an interpolation object based on the optimal frequency pivots
			self.frequency_estimate = interp1d(self.pivot_tps, self.pivot_freq, kind=self.interolation_type, bounds_error=False)
			if min(np.diff(self.pivot_tps))<0.000001:
				print pivots
			if self.verbose: print "neg logLH using",len(self.pivot_tps),"pivots:", self.logLH(self.pivot_freq)

		self.final_pivot_freq=np.zeros_like(self.final_pivot_tps)
		self.final_pivot_freq[first_pivot:last_pivot]=self.pivot_freq			
		self.final_pivot_freq[:first_pivot] = self.final_pivot_freq[first_pivot]
		self.final_pivot_freq[last_pivot:] = self.final_pivot_freq[last_pivot-1]
		self.frequency_estimate = interp1d(self.final_pivot_tps, self.final_pivot_freq, kind=self.interolation_type, bounds_error=False)


class virus_frequencies(object):
	def __init__(self, pc=1e-4 ,dfreq_pc = 1e-2 ,time_interval = (2012.0, 2015.1) ,
				stiffness = 10.0 ,pivots_per_year = 12.0, inertia = 0.7, **kwarks):
		self.pc = pc
		self.dfreq_pc = dfreq_pc
		self.time_interval = time_interval
		self.stiffness = stiffness
		self.pivots_per_year = pivots_per_year
		self.inertia = inertia
		self.pivots = get_pivots(self.time_interval[0], self.time_interval[1], self.pivots_per_year)
		if not hasattr(self, 'nucleotide_frequencies'):
			self.determine_variable_positions()

	def estimate_genotype_frequency(self, aln, gt, threshold = 10):
		'''
		estimate the frequency of a particular genotype specified 
		gt   --		[(position, amino acid), ....]
		'''
		all_dates = [seq.annotations['num_date'] for seq in aln]
		reduced_gt = tuple(aa for pos,aa in gt)
		gts = zip(aln[:,pos] for pos, aa in gt)
		observations = [x==reduced_gt for x in gts]

		all_dates = np.array(all_dates)
		leaf_order = np.argsort(all_dates)
		tps = all_dates[leaf_order]
		obs = np.array(observations)[leaf_order]

		if len(tps)>threshold:
			fe = frequency_estimator(zip(tps, obs), pivots=self.pivots, 
			               stiffness=self.stiffness*float(len(observations))/len(self.viruses), 
		                   logit=True, verbose = 0)
			fe.learn()
			return fe.frequency_estimate, (tps,obs)
		else:
			print "too few observations"
			return None, (tps, obs)

	def get_sub_alignment(self, regions=None):
		from Bio.Align import MultipleSeqAlignment
		sub_aln = []
		all_dates = []
		for seq in self.aa_aln:
			if regions is None or seq.annotations['region'] in regions:
				seq_date = seq.annotations['num_date']
				if seq_date>=self.time_interval[0] and seq_date < self.time_interval[1]:
					sub_aln.append(seq)
					all_dates.append(seq_date)				 
		return MultipleSeqAlignment([sub_aln])

	def determine_mutation_frequencies(self, regions=None, threshold=0.01):
		'''
		determine the abundance of all single nucleotide variants and estimate the 
		frequency trajectory of the top 10, plot those optionally
		'''
		sub_aln = self.get_sub_alignment(regions)
		mutation_frequencies = {"pivots":list(self.pivots)}
		for pos in xrange(sub_aln.get_alignment_length()):
			for ai, aa in self.aa_alphabet:
				if self.aa_frequencies[ai,pos]>threshold and self.aa_frequencies[ai,pos]<1.0-threshold:
					print "estimating freq of ", mut, "total count:", count
					freq, (tps, obs) = self.estimate_genotype_frequency(sub_aln, [(pos, aa)])
					if freq is not None:
						mutation_frequencies[str(pos+1)+aa] = list(np.round(logit_inv(freq.y),3))

	def determine_genotype_frequencies(self, regions=None, threshold=0.1):
		'''
		determine the abundance of all single nucleotide variants and estimate the 
		frequency trajectory of the top 10, plot those optionally
		'''
		sub_aln = self.get_sub_alignment(regions)
		genotype_frequencies = {"pivots":list(self.pivots)}
		relevant_pos = np.where(1.0 - np.aa_frequencies.max(axis=0)>threshold)
		for i1,pos1 in enumerate(relevant_pos[:-1]):
			for pos2 in relevant_pos[i1+1:]:
				for ai1, aa1 in self.aa_alphabet:
					for ai2, aa2 in self.aa_alphabet:
						if self.aa_frequencies[ai1,pos1]>0.3*threshold \
						and self.aa_frequencies[ai2,pos2]<0.3*threshold:
							gt = [(pos1,aa1),(pos2,aa2)]
							print "estimating freq of ", gt, "total count:", count
							freq, (tps, obs) = self.estimate_genotype_frequency(sub_aln, gt)
							gt_label = '/'.join(str(pos+1)+aa] for pos,aa in gt)
							genotype_frequencies[gt_label] = list(np.round(logit_inv(freq.y),3))


	def determine_clade_frequencies(self, clades, regions=None):
		'''
		loop over different clades and determine their frequencies
		returns a dictionary with clades:frequencies
		'''
		sub_aln = self.get_sub_alignment(regions)
		clade_frequencies = {"pivots":list(self.pivots)}

		for ci, (clade_name, clade_gt) in enumerate(clades.iteritems()):
			print "estimating frequency of clade", clade_name, clade_gt
			freq, (tps, obs) = self.estimate_genotype_frequency(sub_aln, [(pos-1, aa) for pos, aa in clade_gt])
			clade_frequencies[clade_name] = list(np.round(logit_inv(freq.y),3))
		return clade_frequencies

	def estimate_sub_frequencies(self, node, all_dates, tip_to_date_index, threshold=50, region_name="global"):
		# extract time points and the subset of observations that fall in the clade.
		tps = all_dates[tip_to_date_index[node.tips]]
		start_index = max(0,np.searchsorted(tps, time_interval[0]))
		stop_index = min(np.searchsorted(tps, time_interval[1]), all_dates.shape[0]-1)
		tps = tps[start_index:stop_index]
		# we estimate frequencies of subclades, they will be multiplied by the 
		# frequency of the parent node and corrected for the frequency of sister clades 
		# already fit
		if node.freq[region_name] is None:
			frequency_left=None
		else:
			frequency_left = np.array(node.freq[region_name])
		ci=0
		# need to resort, since the clade size order might differs after subsetting to regions
		children_by_size = sorted(node.child_nodes(), key = lambda x:len(x.tips), reverse=True)
		for child in children_by_size[:-1]: # clades are ordered by decreasing size
			if len(child.tips)<threshold: # skip tiny clades
				break
			else:
				if debug: print child.num_date, len(child.tips)

				obs = np.in1d(tps, all_dates[tip_to_date_index[child.tips]])

				# make n pivots a year, interpolate frequencies
				# FIXME: adjust stiffness to total number of observations in a more robust manner
				pivots = get_pivots(tps[0], tps[1])
				fe = frequency_estimator(zip(tps, obs), pivots=pivots, stiffness=flu_stiffness*len(all_dates)/2000.0, logit=True)
				fe.learn()

				# assign the frequency vector to the node
				child.freq[region_name] = frequency_left * logit_inv(fe.final_pivot_freq)
				child.logit_freq[region_name] = logit_transform(child.freq[region_name])

				# update the frequency remaining to be explained and prune explained observations
				frequency_left *= (1.0-logit_inv(fe.final_pivot_freq))
				tps_left = np.ones_like(tps,dtype=bool)
				tps_left[obs]=False # prune observations from clade
				tps = tps[tps_left]
			ci+=1

		# if the above loop finished assign the frequency of the remaining clade to the frequency_left
		if ci==len(node.child_nodes())-1 and frequency_left is not None:
			last_child = children_by_size[-1]
			last_child.freq[region_name] = frequency_left
			last_child.logit_freq[region_name] = logit_transform(last_child.freq[region_name])
		else:  # broke out of loop because clades too small. 
			for child in children_by_size[ci:]: # assign freqs of all remaining clades to None.
				child.freq[region_name] = None
				child.logit_freq[region_name] = None
		# recursively repeat for subclades
		for child in node.child_nodes():
			estimate_sub_frequencies(child, all_dates, tip_to_date_index, threshold, region_name)

	def estimate_tree_frequencies(self, threshold = 20, regions=None, region_name = None):
		'''
		loop over nodes of the tree and estimate frequencies of all clade above a certain size
		'''
		all_dates = []
		rootnode = self.tree.seed_node
		# loop over all nodes, make time ordered lists of tips, restrict to the specified regions
		tip_index_region_specific = 0
		if not hasattr(self.tree.seed_node, "virus_count"): self.tree.seed_node.virus_count = {}
		for node in self.tree.postorder_node_iter():
			tmp_tips = []
			if node.is_leaf():
				if regions is None or node.region in regions:
					all_dates.append(node.num_date)
					tmp_tips.append((tip_index_region_specific, node.num_date))
					tip_index_region_specific +=1
			for child in node.child_nodes():
				tmp_tips.extend(child.tips)
			node.tips = np.array([x for x in sorted(tmp_tips, key = lambda x:x[1] )])
			if not hasattr(node, "freq"): node.freq = {}
			if not hasattr(node, "logit_freq"): node.logit_freq = {}

		# erase the dates from the tip lists and cast to int such that they can be used for indexing
		for node in self.tree.postorder_node_iter():
			if len(node.tips.shape)==2:
				node.tips = np.array(node.tips[:,0], dtype=int)
			else:
				node.tips = np.array([], dtype=int)

		# sort the dates and provide a reverse ordering as a mapping of tip indices to dates
		all_dates = np.array(all_dates)
		leaf_order = np.argsort(all_dates)
		reverse_order = np.argsort(leaf_order)
		all_dates = all_dates[leaf_order]

		if regions is None: 
			region_name="global"
		elif region_name is None:
			region_name = ",".join(regions)
		# set the frequency of the root node to 1, the logit frequency to a large value
		rootnode.pivots = get_pivots(time_interval[0], time_interval[1])
		rootnode.virus_count[region_name] = np.histogram(all_dates, bins = rootnode.pivots)
		rootnode.freq[region_name] = np.ones_like(rootnode.pivots)
		rootnode.logit_freq[region_name] = 10*np.ones_like(rootnode.pivots)

		# start estimating frequencies of subclades recursively
		estimate_sub_frequencies(self, rootnode, all_dates, reverse_order, threshold = threshold, region_name = region_name)

	def all_mutations(self, threshold = 0.01):
		self.mutation_frequencies = {}
		for region_label, regions in region_list:
			print "--- "+"determining mutation frequencies in "+region_label+ " "  + time.strftime("%H:%M:%S") + " ---"
			self.mutation_frequencies[region_label] = self.determine_mutation_frequencies(regions, threshold = threshold)


	def all_genotypes(self, threshold = 0.1):
		self.gt_frequencies = {}
		for region_label, regions in region_list:
			print "--- "+"determining genotype frequencies "+region_label+ " "  + time.strftime("%H:%M:%S") + " ---"
			self.genotype_frequencies[region_label] = self.determine_genotype_frequencies(regions, threshold=threshold)


	def all_clades(self):
		clade_frequencies = {}
		for region_label, regions in region_list:
			print "--- "+"determining clade frequencies "+region_label+ " "  + time.strftime("%H:%M:%S") + " ---"
			clade_frequencies[region_label] = self.determine_clade_frequencies(clades, regions=regions)

def test():
	import matplotlib.pyplot as plt
	tps = np.sort(100 * np.random.uniform(size=100))
	freq = [0.1]
	logit = True
	stiffness=100
	s=-0.02
	for dt in np.diff(tps):
		freq.append(freq[-1]*np.exp(-s*dt)+np.sqrt(2*np.max(0,freq[-1]*(1-freq[-1]))*dt/stiffness)*np.random.normal())
	obs = np.random.uniform(size=tps.shape)<freq
	fe = frequency_estimator(zip(tps, obs), pivots=10, stiffness=stiffness, logit=logit)
	fe.learn()
	plt.figure()
	plt.plot(tps, freq, 'o', label = 'actual frequency')
	freq = fe.frequency_estimate(fe.tps)
	if logit: freq = logit_inv(freq)
	plt.plot(fe.tps, freq, '-', label='interpolation')
	plt.plot(tps, (2*obs-1)*0.05, 'o')
	plt.plot(tps[obs], 0.05*np.ones(np.sum(obs)), 'o', c='r', label = 'observations')
	plt.plot(tps[~obs], -0.05*np.ones(np.sum(1-obs)), 'o', c='g')
	plt.plot(tps, np.zeros_like(tps), 'k')
	ws=20
	r_avg = running_average(obs, ws)
	plt.plot(fe.tps[ws/2:-ws/2+1], np.convolve(np.ones(ws, dtype=float)/ws, obs, mode='valid'), 'r', label = 'running avg')
	plt.plot(fe.tps, r_avg, 'k', label = 'running avg')
	plt.legend(loc=2)

def main(tree_fname = 'data/tree_refine.json', clades=None, clades_freq = True, mutation_freq = True, tree_freq = True):
	# load tree
	from io_util import read_json
	plot = debug
	tree =  json_to_dendropy(read_json(tree_fname))
	region_list = [("global", None), ("NA", ["NorthAmerica"]) , ("EU", ["Europe"]), 
			("AS", ["China", "SoutheastAsia", "JapanKorea"]), ("OC", ["Oceania"]) ]

	out_fname = 'data/genotype_frequencies.json'
	gt_frequencies = {}

	if mutation_freq:
		gt_frequencies["mutations"], relevant_pos = all_mutations(tree, region_list, plot)
		write_json(gt_frequencies, out_fname, indent=None)

		gt_frequencies["genotypes"] = all_genotypes(tree, region_list, relevant_pos)
		write_json(gt_frequencies, out_fname, indent=None)

	if clades_freq and clades is not None:
		gt_frequencies["clades"] = all_clades(tree, clades, region_list, plot)

	if clades_freq or mutation_freq:
		# round frequencies
		for gt_type in gt_frequencies:
			for reg in region_list:
				for gt in gt_frequencies[gt_type][reg[0]]:
					tmp = gt_frequencies[gt_type][reg[0]][gt]
					gt_frequencies[gt_type][reg[0]][gt] = [round(x,3) for x in tmp]

		write_json(gt_frequencies, out_fname, indent=None)

	if tree_freq:
		tree_out_fname = 'data/tree_frequencies.json'
		for region_label, regions in region_list:
			print "--- "+"adding frequencies to tree "+region_label+ " "  + time.strftime("%H:%M:%S") + " ---"
			estimate_tree_frequencies(tree, threshold = 10, regions=regions, region_name=region_label)
		write_json(dendropy_to_json(tree.seed_node), tree_out_fname, indent=None)
	return tree_out_fname

if __name__=="__main__":
	#test()
	main()



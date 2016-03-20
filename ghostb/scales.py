import os
import sys
import math
import numpy as np
from ghostb.gen_graph import GenGraph
from ghostb.filter_dists import FilterDists
from ghostb.communities import Communities
from ghostb.borders import Borders
from ghostb.combine_borders import CombineBorders
from ghostb.draw_map import draw_map
from ghostb.confmodel import normalize_with_confmodel
from ghostb.cropborders import CropBorders
from ghostb.voronoi import Voronoi
from ghostb.partition import Partition

    
class Scales:
    def __init__(self, outdir, intervals):
        self.outdir = outdir
        self.intervals = intervals
        self.per_table = None

    def percent_range(self):
        step = 100.0 / self.intervals
        return [int(i * step) for i in range (1, self.intervals + 1)]
        
    def make_path(self, name, per_dist, directory=False):
        path = '%s/%s-d%s' % (self.outdir, name, per_dist)
        if directory:
            if not os.path.exists(path):
                os.makedirs(path)
            return path
        else:
            return '%s.csv' % (path,)

    def graph_path(self, per_dist):
        return self.make_path('graph', per_dist)

    def comm_path(self, per_dist, directory):
        return self.make_path('comm', per_dist, directory)

    def bord_path(self, per_dist):
        return self.make_path('bord', per_dist)

    def map_path(self, per_dist):
        return '%s/map-d%s.pdf' % (self.outdir, per_dist)
    
    def write_percentiles(self, per_table):
        per_file = '%s/percentiles.csv' % self.outdir
        f = open(per_file, 'w')
        f.write('percentile,distance\n')
        for per in per_table:
            f.write('%s,%s\n' % (per, per_table[per]))
        f.close()
    
    def compute_percentiles(self, infile):
        per_table = {}
        
        print('loading file: %s' % infile)
        data = np.genfromtxt(infile, names=['dist', 'time'], skip_header=1, delimiter=',')
        # print('computing percentiles...')
        for per in self.percent_range():
            dist_per = np.percentile(data['dist'], per)
            per_table[per] = dist_per
            # print('[percentile %s] dist: %s' % (per, dist_per))

        # print('writing percentiles...')
        self.write_percentiles(per_table)
        return per_table

    def percentile2dist(self, infile, per):
        if self.per_table is None:
            self.per_table = self.compute_percentiles(infile)
        return self.per_table[per]
    
    def abs_log_scale(self, per):
        max_dist = 100.
        return math.pow(float(per) / 100., 2) * max_dist
    
    def dist(self, per, scale, infile):
        if scale == 'percentiles':
            return self.percentile2dist(infile, per)
        elif scale == 'log':
            return self.abs_log_scale(per)
        else:
            print('Unknown scale type: %s' % scale)
            sys.exit()
    
    def generate_graphs(self, db, infile, scale, table):
        fd = FilterDists(db)
        
        graph_file = self.graph_path(100)
        print('generating: %s' % graph_file)
        gg = GenGraph(db, graph_file=graph_file, table=table)
        gg.generate()

        for per in self.percent_range():
            if per < 100:
                filtered_file = self.graph_path(per)
                print('generating: %s' % filtered_file)
                max_dist = self.dist(per, scale, infile)
                fd.filter(graph_file, filtered_file, max_dist)

        print('done.')

    def normalize(self):
        for per_dist in self.percent_range():
            graph_file = self.graph_path(per_dist)
            normalize_with_confmodel(graph_file, graph_file)
        
    def generate_communities(self, two, runs, best):
        fname = '%s/metrics.csv' % self.outdir
        f = open(fname, 'w')
        f.write('per_distance,modularity,ncomms\n')
        for per_dist in self.percent_range():
            graph_file = self.graph_path(per_dist)
            comm = Communities(graph_file)
            comm_file = self.comm_path(per_dist, False)
            comm_dir = self.comm_path(per_dist, True)
            modul, ncomms = comm.compute_n_times(
                comm_dir, comm_file, two, runs, best)
            f.write('%s,%s,%s\n' % (per_dist, modul, ncomms))
        f.close()

    def generate_borders(self, db, best, smooth):
        bord = Borders(db, smooth)
        for per_dist in self.percent_range():
            bord_file = self.bord_path(per_dist)
            if best:
                comm_file = self.comm_path(per_dist, False)
                bord.process(None, comm_file, bord_file)
            else:
                comm_dir = self.comm_path(per_dist, True)
                bord.process(comm_dir, None, bord_file)

    def rand_index_seq(self, db):
        window = 1
        percentiles = self.percent_range()

        # voronoi
        vor = Voronoi(db)
        
        # read all partitions
        pars = {}
        for per in percentiles:
            comm_file = self.comm_path(per, False)
            par = Partition(vor, comm_file)
            par.read(comm_file)
            par.smooth_until_stable()
            pars[per] = par

        steps = len(percentiles)
        for i in range(window, steps):
            dist = 0.
            per1 = percentiles[i]
            par1 = pars[per]
            for j in range(0, window):
                per2 = percentiles[i - j - 1]
                par2 = pars[per2]
                dist += par1.distance(par2)
            dist /= window

            print("%s,%s" % (per1, dist))

    def metric(self, metric, db, smooth, scale, infile):
        vor = Voronoi(db)
        
        for per in self.percent_range():
            dir_in = self.comm_path(per, True)
            f_ins = []
            for (dirpath, dirnames, filenames) in os.walk(dir_in):
                f_ins.extend(filenames)
            m = 0.
            for f in f_ins:
                par = Partition(vor)
                par.read("%s/%s" % (dir_in, f))
                if smooth:
                    par.smooth_until_stable()
                m += par.metric(metric)
            m /= float(len(f_ins))
            print("%s,%s,%s" % (per, self.dist(per, scale, infile), m))
            
    def generate_multi_borders(self, db, out_file, smooth):
        files = [self.comm_path(i, False) for i in self.percent_range()]
        b = Borders(db, smooth)
        b.process_multi(files, self.percent_range(), out_file)
                
    def crop_borders(self, shapefile):
        for per_dist in self.percent_range():
            bord_file = self.bord_path(per_dist)
            print('Cropping: %s' % bord_file)
            cropper = CropBorders(bord_file, shapefile)
            cropper.crop()
            cropper.write(bord_file)
                    
    def combine_borders(self, out_file):
        cb = CombineBorders()
        for per_dist in self.percent_range():
            bord_file = self.bord_path(per_dist)
            cb.add_file(bord_file, per_dist)
        cb.write(out_file)
                
    def generate_maps(self, region):
        for per_dist in self.percent_range():
            bord_file = self.bord_path(per_dist)
            map_file = self.map_path(per_dist)
            print('drawing map: %s' % map_file)
            draw_map(bord_file, map_file, region, osm=True)

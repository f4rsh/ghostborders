#!/bin/bash

ghostb --db $1 --infile $1-norm/dists.csv --outdir $1-norm scales_normalize
ghostb --outdir $1-norm --best scales_communities
ghostb --db $1 --outdir $1-norm --outfile $1-norm/borders.csv --best --scales 25,50,75,100 --smooth scales_multi_borders
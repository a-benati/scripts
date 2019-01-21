#!/usr/bin/env python

# Plot LOFAR weights
# Update LOFAR weights using residual visibilities
#
# Author: Francesco de Gasperin
# Credits: Frits Sweijen, Etienne Bonnassieux

import os, sys, logging, time
import numpy as np
from casacore.tables import taql, table
import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt

from lib_timer import Timer

class MShandler():
    def __init__(self, ms_file):
        """
        ms_file: a MeasurementSet file
        """
        logging.info('Reading: %s' % ms_file)
        self.ms_file = ms_file
        self.ms = table(ms_files[0], readonly=False, ack=False)

    def get_flags_aggr(self):
        """
        """
        ms = self.ms_file
        return taql('select NTRUES(GAGGR(FLAG), [0, 2]) as FLAG, SHAPE(GAGGR(FLAG)) as N from $ms where ANTENNA1 != ANTENNA2 groupby TIME')

    def get_flags(self):
        """
        """
        ms = self.ms_file
        return taql('select FLAG from $ms where ANTENNA1 != ANTENNA2')


def flagonmindata(MSh, mode, fract):
    t = MSh.get_flags_aggr()
    f = t.getcol('FLAG').astype(float)
    n = t.getcol('N')
    ntime = len(n)
    nbl = n[0,0]
    nchan = n[0,1]
    npol = n[0,2]
    ff = f/(nbl*npol) # fraction of flagged data per timestep and chan
    fffullyflag = np.array(ff == 1.)
    ff = np.array(ff > fract, dtype=bool)
    logging.info( "Fully flagged timestep/chan: %i -> %i (%f%%)" % ( np.sum(fffullyflag), np.sum(ff), 100*np.sum(ff)/float(np.size(ff)) ) ) 
    ff = np.repeat(ff, nbl, axis=0) # repeat time axis for nbl times
    ff = np.expand_dims(ff, axis=2) # add pol axis
    ff = np.repeat(ff, npol, axis=2) # repeat new pol axis for npol times
    msflag = MSh.get_flags()
    ff = np.array(ff | msflag.getcol('FLAG'), dtype=bool)
    msflag.putcol('FLAG', ff)
    msflag.flush()


def readArguments():
    import argparse
    parser=argparse.ArgumentParser("Flag data that do not come with enough unflagged data.")
    parser.add_argument("-v", "--verbose", help="Be verbose. Default is False", required=False, action="store_true")
    parser.add_argument("-m", "--mode", type=str, help="Mode can be: NO MODE IMPLEMENTED", required=False, default=None)
    parser.add_argument("-f", "--fractbad", type=float, help="Fraction of bad data allowed, if higher flagging is triggered (default 0.5) ", required=False, default=0.5)
    parser.add_argument("ms_files", type=str, help="MeasurementSet name(s).", nargs="+")
    args=parser.parse_args()
    return vars(args)

if __name__=="__main__":
    start_time = time.time()

    args         = readArguments()
    verbose      = args["verbose"]
    mode         = args["mode"]
    fract        = args["fractbad"]
    ms_files     = args["ms_files"]

    if mode != 'residual' and mode != 'subchan' and mode != 'subtime' and mode is not None:
        logging.error('Unknown mode: %s' % mode)
        sys.exit()

    if verbose: logging.basicConfig(level=logging.DEBUG)
    else: logging.basicConfig(level=logging.INFO)

    logging.info('Reading MSs...')
    MSh = MShandler(ms_files)

    logging.info('Extend flags (fraction: %f)...' % fract)
    flagonmindata(MSh, mode, fract)

    logging.debug('Running time %.0f s' % (time.time()-start_time))

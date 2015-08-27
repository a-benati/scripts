#!/usr/bin/python
# perform self-calibration on a group of SBs concatenated in TCs. Script must be run in dir with MS.
# number/chan in MS are flexible but the must be concatenable (same chans/freq!)
# Input:
# TCs are blocks of SBs should have calibrator corrected (a+p) data in DATA (beam not applied).
# file format of TCs is: group#_TC###.MS.
# Output:
# TCs with selfcal corrected source subtracted data in SUBTRACTED_DATA
# instrument tables contain gain (slow) + fast (scalarphase+TEC) solutions
# last high/low resolution models are copied in the "self/models" dir
# last high/low resolution images are copied in the "self/images" dir

skymodel = '/home/fdg/scripts/autocal/1RXSJ0603_LBA/toothbrush.GMRT150.skymodel'

#######################################################################################

import sys, os, glob, re
import numpy as np
from lofar import bdsm
import pyrap.tables as pt
import lsmtool
from lib_pipeline import *
from make_mask import make_mask

set_logger()
s = Scheduler(qsub=True, max_threads=32, dry=False)

# here an image+model for each group will be saved
if not os.path.exists('self/images'): os.makedirs('self/images')
if not os.path.exists('self/models'): os.makedirs('self/models')

for group in sorted(glob.glob('group*'))[::-1]:

    mss = sorted(glob.glob(group+'/group*_TC*.MS'))
    g = str(re.findall(r'\d+', mss[0])[0])
    logging.info('Working on group: '+g+'...')
    concat_ms = group+'/concat.MS'
    
    ################################################################################################
    # Clear
    logging.info('Cleaning...')
    check_rm(group+'/*log *log *bak')
    check_rm(group+'/plot* plot')
    check_rm(group+'/*h5 *h5')
    check_rm('*last')
    check_rm('img')
    os.makedirs('img')
    check_rm('self/images/g'+g)
    os.makedirs('self/images/g'+g)
    
    #################################################################################################
    # TODO: useless? why add columns by hand gives problems?
    logging.info('Creating fake parmdb...')
    for ms in mss:
        s.add('calibrate-stand-alone -f --parmdb-name instrument '+ms+' /home/fdg/scripts/autocal/1RXSJ0603_LBA/parset_self/bbs-fakeparmdb.parset '+skymodel, \
              log=ms+'_fakeparmdb.log', cmd_type='BBS')
    s.run(check=True)

    logging.info('Creating MODEL_DATA_HIGHRES...')
    for ms in mss:
        s.add('addcol2ms.py -i '+ms+' -o MODEL_DATA_HIGHRES', log=ms+'_addcol.log', cmd_type='python')
    s.run(check=True)

    # after columns creation
    logging.info('Concatenating TCs...')
    pt.msutil.msconcat(mss, concat_ms, concatTime=False)
    
    ####################################################################################################
    # self-cal cycle
    for i in xrange(3):
        logging.info('Start selfcal cycle: '+str(i))
    
        # TEST for circular
        # separate LL and RR
        #msLL = ms.replace('.MS','-LL.MS')
        #if os.path.exists(msLL): os.system('rm -r '+msLL)
        #msRR = ms.replace('.MS','-RR.MS')
        #if os.path.exists(msRR): os.system('rm -r '+msRR)
        #os.system( 'cp -r '+ms+' '+msLL )
        #os.system( 'mv '+ms+' '+msRR )
        #print 'taql \'update '+msRR+' set DATA[,3]=DATA[,0]\''
        #os.system( 'taql \'update '+msRR+' set DATA[,3]=DATA[,0]\'' )
        #print 'taql \'update '+msLL+' set DATA[,0]=DATA[,3]\''
        #os.system( 'taql \'update '+msLL+' set DATA[,0]=DATA[,3]\'' )
    
        if i == 0:
            # calibrate phase-only - group*_TC.MS:DATA (beam: ARRAY_FACTOR) -> group*_TC.MS:CORRECTED_DATA (selfcal phase corrected, beam corrected)
            logging.info('Calibrating phase...')
            for ms in mss:
                s.add('calibrate-stand-alone -f '+ms+' /home/fdg/scripts/autocal/1RXSJ0603_LBA/parset_self/bbs-solcor.parset '+skymodel, \
                      log=ms+'_cal-c'+str(i)+'.log', cmd_type='BBS')
            s.run(check=True)
        else:
            # calibrate phase-only - group*_TC.MS:DATA @ MODEL_DATA -> group*_TC.MS:CORRECTED_DATA_PHASE (selfcal phase corrected, beam corrected)
            logging.info('Calibrating phase...')
            for ms in mss:
                s.add('calibrate-stand-alone -f --parmdb-name instrument_csp '+ms+' /home/fdg/scripts/autocal/1RXSJ0603_LBA/parset_self/bbs-solcor_csp.parset '+skymodel, \
                      log=ms+'_calpreamp-c'+str(i)+'.log', cmd_type='BBS')
            s.run(check=True)
    
            # calibrate amplitude (only solve) - group*_TC.MS:CORRECTED_DATA_PHASE @ MODEL_DATA
            logging.info('Calibrating amplitude...')
            for ms in mss:
                s.add('calibrate-stand-alone -f --parmdb-name instrument_amp '+ms+' /home/fdg/scripts/autocal/1RXSJ0603_LBA/parset_self/bbs-sol_amp.parset '+skymodel, \
                      log=ms+'_calamp-c'+str(i)+'.log', cmd_type='BBS')
            s.run(check=True)

            # merge parmdbs
            logging.info('Merging instrument tables...')
            for ms in mss:
                merge_parmdb(ms+'/instrument_csp', ms+'/instrument_amp', ms+'/instrument', clobber=True)
    
            ########################################################
            # LoSoTo Amp rescaling
            logging.info('LoSoTo...')
            os.makedirs('plot')
            check_rm('globaldb')
            os.makedirs('globaldb')
            for num, ms in enumerate(mss):
                os.system('cp -r '+ms+'/instrument globaldb/instrument-'+str(num))
                if num == 0: os.system('cp -r '+ms+'/ANTENNA '+ms+'/FIELD '+ms+'/sky globaldb/')
            h5parm = 'global-c'+str(i)+'.h5'

            s.add('H5parm_importer.py -v '+h5parm+' globaldb', log='losoto-c'+str(i)+'.log', cmd_type='python')
            s.run(check=False)
            s.add('losoto -v '+h5parm+' /home/fdg/scripts/autocal/1RXSJ0603_LBA/parset_self/losoto.parset', log='losoto-c'+str(i)+'.log', log_append=True, cmd_type='python')
            s.run(check=False)
            s.add('H5parm_exporter.py -v -c '+h5parm+' globaldb', log='losoto-c'+str(i)+'.log', log_append=True, cmd_type='python')
            s.run(check=True)

            for num, ms in enumerate(mss):
                check_rm(ms+'/instrument')
                os.system('mv globaldb/sol000_instrument-'+str(num)+' '+ms+'/instrument')
            os.system('mv plot '+group+'/plot-c'+str(i))
            os.system('mv '+h5parm+' '+group)
        
            # correct - group*_TC.MS:DATA -> group*_TC.MS:CORRECTED_DATA (selfcal phase+amp corrected, beam corrected)
            logging.info('Correcting...')
            for ms in mss:
                s.add('calibrate-stand-alone '+ms+' /home/fdg/scripts/autocal/1RXSJ0603_LBA/parset_self/bbs-cor_ampcsp.parset '+skymodel, \
                      log=ms+'_corampcsp-c'+str(i)+'.log', cmd_type='BBS')
#                s.add('NDPPP /home/fdg/scripts/autocal/1RXSJ0603_LBA/parset_self/NDPPP-cor_ampcsp.parset msin='+ms+' \
#                      cor3.parmdb='+ms+'/instrument', \
#                      log=ms+'_corampcsp-c'+str(i)+'.log', cmd_type='NDPPP')
            s.run(check=True)
    
        # TEST for circular
        # join RR and LL
        #if os.path.exists(ms): os.system('rm -r '+ms)
        #os.system('mv '+msRR+' '+ms)
        #print 'taql \'update '+ms+', '+msLL+' as ll set DATA[3,]=ll.DATA[3,]\''
        #os.system('taql \'update '+ms+', '+msLL+' as ll set DATA[3,]=ll.DATA[3,]\'')
        #os.system('rm -r '+msLL)
    
        ###################################################################################################################
        # concat all TCs in one MS - group*_TC.MS:CORRECTED_DATA -> concat.MS:CORRECTED_DATA (selfcal corrected, beam corrected)
    
        # clean mask clean (cut at 8k lambda) - MODEL_DATA updated
        logging.info('Cleaning 1...')
        imagename = 'img/wide-'+str(i)
        s.add('wsclean -reorder -name ' + imagename + ' -size 5000 5000 -mem 90 \
                -scale 5arcsec -weight briggs 0.0 -niter 100000 -mgain 0.75 -no-update-model-required -maxuv-l 8000 '+concat_ms, \
                log='wscleanA-c'+str(i)+'.log', cmd_type='wsclean')
        s.run(check=True)
        make_mask(image_name = imagename+'-image.fits', mask_name = imagename+'.newmask')
        s.add_casa('/home/fdg/scripts/autocal/casa_comm/casa_blank.py', \
                   params={'imgs':imagename+'.newmask', 'region':'/home/fdg/scripts/autocal/1RXSJ0603_LBA/tooth_mask.crtf', 'setTo':1}, log='casablank-c'+str(i)+'.log')
        s.run(check=True)
        logging.info('Cleaning 2...')
        s.add('wsclean -reorder -name ' + imagename + '-masked -size 5000 5000 -mem 90 \
                -scale 5arcsec -weight briggs 0.0 -niter 20000 -mgain 0.75 -update-model-required -maxuv-l 8000 -casamask '+imagename+'.newmask '+concat_ms, \
                log='wscleanB-c'+str(i)+'.log', cmd_type='wsclean')
        s.run(check=True)
       
        logging.info('Moving MODEL_DATA to MODEL_DATA_HIGHRES...')
        s.add('taql "update '+concat_ms+' set MODEL_DATA_HIGHRES = MODEL_DATA"', log='taql1-c'+str(i)+'.log')
        s.run(check=False)
    
        ####################################################################
        # FAST VERSION (no low-res)
        #continue
        ####################################################################
    
        ############################################################################################################
        # Subtract model from all TCs - concat.MS:CORRECTED_DATA - MODEL_DATA -> concat.MS:CORRECTED_DATA (selfcal corrected, beam corrected, high-res model subtracted)
        logging.info('Subtracting high-res model (CORRECTED_DATA = CORRECTED_DATA - MODEL_DATA)...')
        s.add('taql "update '+concat_ms+' set CORRECTED_DATA = CORRECTED_DATA - MODEL_DATA"', log='taql2-c'+str(i)+'.log')
        s.run(check=False)

        # reclean low-resolution
        logging.info('Cleaning low resolution 1...')
        imagename = 'img/wide-lr-'+str(i)
        s.add('wsclean -reorder -name ' + imagename + ' -size 4000 4000 -mem 90\
                -scale 15arcsec -weight briggs 0.0 -niter 50000 -mgain 0.75 -no-update-model-required -maxuv-l 2500 '+concat_ms, \
                log='wscleanA-lr-c'+str(i)+'.log', cmd_type='wsclean')
        s.run(check=True)
        make_mask(image_name = imagename+'-image.fits', mask_name = imagename+'.newmask', threshpix=6) # a bit higher treshold
        logging.info('Cleaning low resolution 2...')
        s.add('wsclean -reorder -name ' + imagename + '-masked -size 4000 4000 -mem 90\
                -scale 15arcsec -weight briggs 0.0 -niter 10000 -mgain 0.75 -update-model-required -maxuv-l 2500 -casamask '+imagename+'.newmask '+concat_ms, \
                log='wscleanB-lr-c'+str(i)+'.log', cmd_type='wsclean')
        s.run(check=True)

        ###############################################################################################################
        # Subtract low-res model - concat.MS:CORRECTED_DATA - MODEL_DATA -> concat.MS:CORRECTED_DATA (empty)
        logging.info('Subtracting low-res model (CORRECTED_DATA = CORRECTED_DATA - MODEL_DATA)...')
        s.add('taql "update '+concat_ms+' set CORRECTED_DATA = CORRECTED_DATA - MODEL_DATA"', log='taql3-c'+str(i)+'.log')
        s.run(check=False)

        # Flag on residuals
        logging.info('Flagging residuals...')
        for ms in mss:
            s.add('NDPPP /home/fdg/scripts/autocal/1RXSJ0603_LBA/parset_self/NDPPP-flag.parset msin='+ms, \
                    log=ms+'_flag-c'+str(i)+'.log', cmd_type='NDPPP')
        s.run(check=True)
    
        # Concat models
        logging.info('Adding model data columns (MODEL_DATA = MODEL_DATA_HIGHRES + MODEL_DATA)...')
        s.add('taql "update '+concat_ms+' set MODEL_DATA = MODEL_DATA_HIGHRES + MODEL_DATA"', log='taql4-c'+str(i)+'.log')
        s.run(check=False)
    
    # Subtract of the best model (currupted) - group*_TC*.MS:DATA - MODEL_DATA -> group*_TC*.MS:SUBTRACTED_DATA (not corrected data - all source subtracted, beam corrected, circular)
    #                                        - group*_TC*.MS:DATA -> group*_TC*.MS:CORRECTED_DATA (corrected data - all source subtracted, beam corrected, circular)
    # TODO: move to NDPPP
    logging.info('Final subtraction...')
    for ms in mss:
        s.add('calibrate-stand-alone --replace-sourcedb '+ms+' /home/fdg/scripts/autocal/1RXSJ0603_LBA/parset_self/bbs-subfinal.parset '+skymodel, \
               log=ms+'_final-sub.log', cmd_type='BBS')
    s.run(check=True)

    # re-create concat because SUBTRACTED_DATA has just been created
    logging.info('Concatenating TCs...')
    check_rm(concat_ms)
    pt.msutil.msconcat(mss, concat_ms, concatTime=False)
 
    # Perform a final clean to create an inspection image which should be very empty
    logging.info('Empty cleaning...')
    imagename = 'img/empty'
    s.add('wsclean -reorder -name ' + imagename + ' -size 5000 5000 \
            -scale 5arcsec -weight briggs 0.0 -niter 1 -mgain 0.75 -no-update-model-required -maxuv-l 8000 -datacolumn CORRECTED_DATA '+concat_ms, \
            log='wscleanA-c'+str(i)+'.log', cmd_type='wsclean')
    s.run(check=True)
    
    # Copy last *model
    logging.info('Copying models/images...')
    os.system('mv img/wide-'+str(i)+'-masked-model.fits self/models/wide-g'+g+'.model')
    os.system('mv img/wide-lr-'+str(i)+'-masked-model.fits self/models/wide-lr-g'+g+'.model')
    # Copy images
    [ os.system('mv img/wide-'+str(i)+'.newmask self/images/g'+g) for i in xrange(3) ]
    [ os.system('mv img/wide-lr-'+str(i)+'.newmask self/images/g'+g) for i in xrange(3) ]
    [ os.system('mv img/wide-'+str(i)+'-image.fits self/images/g'+g) for i in xrange(3) ]
    [ os.system('mv img/wide-lr-'+str(i)+'-image.fits self/images/g'+g) for i in xrange(3) ]
    [ os.system('mv img/wide-'+str(i)+'-masked-image.fits self/images/g'+g) for i in xrange(3) ]
    [ os.system('mv img/wide-lr-'+str(i)+'-masked-image.fits self/images/g'+g) for i in xrange(3) ]
    os.system('mv img/empty-image.fits self/images/g'+g)
    os.system('mv *log '+group)

logging.info("Done.")
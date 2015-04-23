#!/usr/bin/env python

# create a mask using bdsm of an image

def make_mask(image_name, threshpix=5, threshisl=3, atrous_do=False, mask_name=None, rmsbox=(120,40), mask_combine=None):

    import sys, os, numpy
    import pyfits, pyrap
    import lofar.bdsm as bdsm

    # DO THE SOURCE DETECTION
    print "Running source detector"
    img = bdsm.process_image( image_name, mean_map='zero', adaptive_rms_box=True, rms_box_bright=(20, 7), rms_box=rmsbox,\
        thresh_pix=int(threshpix), thresh_isl=int(threshisl), atrous_do=atrous_do, ini_method='curvature', advanced_opts=True, blank_limit=1e-5)

    # DEBUG
    #soumodel = image_name.replace('.image','.skymodel')
    #if os.path.exists(soumodel): os.system('rm ' + soumodel)
    #img.export_image(img_type='sou_model', outfile=soumodel)

    # WRITE THE GAUSSIAN MODEL FITS
    gausmodel = image_name.replace('.image','.gausmodel').replace('.restored.corr','.gausmodel').replace('.fits','.gausmodel')
    assert gausmodel != image_name # prevent overwriting
    if os.path.exists(gausmodel): os.system('rm ' + gausmodel)
    img.export_image(img_type='gaus_model', outfile=gausmodel)

    hdulist = pyfits.open(gausmodel)
    pixels_gs = hdulist[0].data

    # convert to casa-image if fits file
    if image_name[-4:] == 'fits':
        print "Converting to fits file..."
        img = pyrap.images.image(image_name)
        image_name = image_name.replace('.fits','.image')
        img.saveas(image_name, overwrite=True)
        del img

    if mask_name == None: mask_name = image_name.replace('.image','.mask').replace('.restored.corr','.mask')
    print 'Making mask:', mask_name
    if os.path.exists(mask_name): os.system('rm -r ' + mask_name)
    os.system('cp -r ' + image_name + ' ' + mask_name)

    img = pyrap.images.image(mask_name)
    pixels = numpy.copy(img.getdata())
    pixels_mask = 0. * numpy.copy(pixels)

    gs_cut = 1e-5
    idx = numpy.where(pixels_gs > gs_cut)
    pixels_mask[idx] = 1.
    
    # do an pixel-by-pixel "OR" operation with a given mask
    if mask_combine != None:
        print "Combining with "+mask_combine
        imgcomb = pyrap.images.image(mask_combine)
        assert imgcomb.shape() == img.shape()
        pixels_mask[numpy.where(imgcomb.getdata() == 1.)] = 1.

    img.putdata(pixels_mask)
    del img

    return mask_name

if __name__=='__main__':
    import optparse
    opt = optparse.OptionParser(usage='%prog [-v|-V] imagename \n Francesco de Gasperin', version='1.0')
    opt.add_option('-p', '--threshpix', help='Threshold pixel (default=5)', type='int', default=5)
    opt.add_option('-i', '--threshisl', help='Threshold island (default=3)', type='int', default=3)
    opt.add_option('-t', '--atrous_do', help='BDSM extended source detection (default=False)', action='store_true', default=False)
    opt.add_option('-m', '--newmask', help='Mask name (default=imagename with mask in place of image)', default=None)
    opt.add_option('-c', '--combinemask', help='Mask name of a mask to add to the found one (default=None)', default=None)
    opt.add_option('-r', '--rmsbox', help='rms box size (default=120,40)', default='120,40')
    (options, args) = opt.parse_args()
    
    rmsbox = (int(options.rmsbox.split(',')[0]),int(options.rmsbox.split(',')[1]))
    make_mask(args[0].rstrip('/'), options.threshpix, options.threshisl, options.atrous_do, options.newmask, rmsbox, options.combinemask)

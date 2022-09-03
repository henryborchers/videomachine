#!/usr/bin/env python
# -*- coding: utf-8 -*-
# DVD Transcoder
#Version History
#   0.1.0 - 20220902
#       New versio that just cats the vobs using bash then transcodes from there lol
#
#
#
# import modules used here -- sys is a very standard one
import os, sys
import datetime
import csv                          # used for creating the csv
import subprocess                   # used for running ffmpeg, qcli, and rsync
import shlex                        # used for properly splitting the ffmpeg/rsync strings
import argparse                     # used for parsing input arguments
import time

def main():


    media_info_list = []

    ####init the stuff from the cli########
    parser = argparse.ArgumentParser(description="dvd_transcoder version 0.1.0: Creates a concatenatd video file from an DVD-Video ISO")
    parser.add_argument('-i','--input',dest='i', help="the path to the input directory or files")
    parser.add_argument('-f','--format',dest='f', help="The output format (defaults to v210. Pick from v210, ProRes, H.264, FFv1)")
    parser.add_argument('-o','--output',dest='o', help="the output file path (optional, defaults to the same as the input)")
    parser.add_argument('-v','--verbose',dest='v',action='store_true',default=False,help='run in verbose mode (including ffmpeg info)')
    #parser.add_argument('-c','--csvname',dest='c', help="the name of the csv file (optional)")
    args = parser.parse_args()


    #handling the input args. This is kind of a mess in this version
    if args.i is None:
        print bcolors.FAIL + "Please enter an input file!" + bcolors.ENDC
        quit()
    if args.f is None:
        output_format = "v210"
        transcode_string = " -movflags write_colr+faststart -color_primaries smpte170m -color_trc bt709 -colorspace smpte170m -color_range mpeg -vf 'setfield=bff,setdar=4/3' -c:v v210 -c:a pcm_s24l -ar 4800 "
        output_ext = ".mov"
    elif "v210" in args.f:
        output_format = "v210"
        transcode_string = " -movflags write_colr+faststart -color_primaries smpte170m -color_trc bt709 -colorspace smpte170m -color_range mpeg -vf 'setfield=bff,setdar=4/3' -c:v v210 -c:a pcm_s24l -ar 48000 "
        output_ext = ".mov"
    elif "ProRes" in args.f:
        output_format = "ProRes"
        transcode_string = " -c:v prores -profile:v 3 -c:a pcm_s24le -ar 48000 "
        output_ext = ".mov"
    elif "H.264" in args.f:
        output_format = "H.264"
        transcode_string = " -c:v libx264 -pix_fmt yuv420p -movflags faststart -b:v 3500000 -b:a 160000 -ar 48000 -s 640x480 -vf yadif "
        output_ext = ".mp4"
    elif "FFv1" in args.f:
        output_format = "FFv1"
        transcode_string = " -map 0 -dn -c:v ffv1 -level 3 -coder 1 -context 1 -g 1 -slicecrc 1 -slices 24 -field_order bb -color_primaries smpte170m -color_trc bt709 -colorspace smpte170m -c:a copy "
        output_ext = ".mkv"
    else:
        output_format = "v210"
        transcode_string = " -movflags write_colr+faststart -color_primaries smpte170m -color_trc bt709 -colorspace smpte170m -color_range mpeg -vf 'setfield=bff,setdar=4/3' -c:v v210 -c:a pcm_s24l -ar 48000 "
        output_ext = ".mov"
    if args.o is None:
        output_path = os.path.dirname(args.i) + "/"

    if args.v:
        ffmpeg_command = "/usr/local/bin/ffmpeg "
        print "Running in Verbose Mode"
    else:
        ffmpeg_command = "/usr/local/bin/ffmpeg -hide_banner -loglevel panic "


    #print "Removing Temporary Files"

    #This parts mounts the iso
    print "Mounting ISO..."
    mount_point = mount_Image(args.i)
    print "Finished Mounting ISO!"

    ##this part processes the vobs

    ##move each vob over as a seperate file, adding each vob to a list to be concatenated
    print "Moving VOBs to Local directory..."
    if move_VOBS_to_local(args.i, mount_point, ffmpeg_command):
        print "Finished moving VOBs to local directory!"
    else:
        print "No VOBs found. Quitting!"

    #concatenate vobs into a sungle file, format of the user's selection
    #concatenate_VOBS(args.i, transcode_string, output_ext, ffmpeg_command)

    #transcode vobs into the target format
    transcode_VOBS(args.i, transcode_string, output_ext, ffmpeg_command)

    #CLEANUP
    print "Removing Temporary Files..."
    #Delete all fo the leftover files
    #os.remove(args.i + ".mylist.txt")
    for the_file in os.listdir(args.i + ".VOBS"):
        file_path = os.path.join(args.i + ".VOBS", the_file)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
            #elif os.path.isdir(file_path): shutil.rmtree(file_path)
        except Exception as e:
            print(e)
    os.rmdir(args.i + ".VOBS")
    print "Finished Removing Temporary Files!"

    #This parts unmounts the iso
    print "Unmounting ISO"
    unmount_Image(mount_point)
    print "Finished Unmounting ISO!"

    return


def mount_Image(ISO_Path):
    mount_point_exists = True
    mount_increment = 0

    ##figure out what the mountpoint will be
    while mount_point_exists:
        mount_point = "ISO_Volume_" + str(mount_increment)
        mount_point_exists = os.path.isdir("/Volumes/" + mount_point)
        mount_increment = mount_increment + 1

    ##mount ISO
    mount_point = "/Volumes/" + mount_point
    mount_command = "hdiutil attach '" + ISO_Path + "' -mountpoint " + mount_point
    os.mkdir(mount_point)
    hdiutil_return = run_command(mount_command)
    if hdiutil_return == 1:
        print("Mounting Failed. Quitting Script")
        quit()
    return mount_point


def unmount_Image(mount_point):
    unmount_command = "hdiutil detach '" + mount_point + "'"
    run_command(unmount_command)
    ##os.remove(mount_point) thought we needed this but i guess not...
    return True



def move_VOBS_to_local(first_file_path, mount_point, ffmpeg_command):

    file_name_root = (os.path.splitext(os.path.basename(first_file_path))[0])
    input_vobList = []
    input_discList = []
    lastDiscNum = 1

    #find all of the vobs we want to concatenate
    for dirName, subdirList, fileList in os.walk(mount_point):
        for fname in fileList:
            if fname.split("_")[0] == "VTS" and fname.split(".")[-1] == "VOB":
                discNum = fname.split("_")[1]
                discNumInt = discNum.split("_")[0]
                vobNum = fname.split("_")[-1]
                vobNum = vobNum.split(".")[0]
                vobNumInt = int(vobNum)
                discNumInt = int(discNum)
                if discNumInt == lastDiscNum:
                    if vobNumInt > 0:
                        input_vobList.append(dirName + "/" + fname)
                if discNumInt > lastDiscNum:
                    input_vobList.sort()
                    input_discList.append(input_vobList)
                    input_vobList = []
                    if vobNumInt > 0:
                        input_vobList.append(dirName + "/" + fname)
                lastDiscNum = discNumInt


    ##Returns False if there are no VOBs found, otherwise it moves on
    if len(input_vobList) == 0:
        has_vobs = False
    else:
        has_vobs = True
        input_vobList.sort()
        input_discList.append(input_vobList)

      ##this portion performs the copy of the VOBs to the local storage. They are moved using the cat bash command

    try:
        delset_path = os.path.dirname(first_file_path)
        os.mkdir(first_file_path + ".VOBS/")
    except OSError:
        pass

#       Creating the cat command here

    cat_command = ""
    output_disc_count = 1
    out_vob_path = first_file_path + ".VOBS/" + file_name_root

    if len(input_discList) > 1:

        for disc in input_discList:
            cat_command += "/bin/cat "
            for vob in disc:
                cat_command += vob + " "
            cat_command += "> '" + out_vob_path + "_" + str(output_disc_count) + ".vob' && "
            output_disc_count += 1

        cat_command = cat_command.strip(" &&")

    else:
        cat_command += "cat "
        for disc in input_discList:
            for vob in disc:
                cat_command += vob + " "
            cat_command += "> '" + out_vob_path + ".vob'"

    run_command(cat_command)


# Everything down here is the old way of doing

#    input_vobList_length = len(input_vobList)
#    iterCount = 1
#    for v in input_vobList:
#        v_name = v.split("/")[-1]
#        out_vob_path = first_file_path + ".VOBS/" + v_name
        #ffmpeg_vob_copy_string = ffmpeg_command + " -i " + v + " -map 0:v:0 -map 0:a:0 -f vob -b:v 9M -b:a 192k -y '" + out_vob_path + "'"        #original without more recent additions
        #ffmpeg_vob_copy_string = ffmpeg_command + " -i " + v + " -map 0:v:0 -map 0:a:0 -video_track_timescale 90000 -f vob -b:v 9M -b:a 192k -y '" + out_vob_path + "'"    #version with just tbs fix
        #ffmpeg_vob_copy_string = ffmpeg_command + " -i " + v + " -map 0:v:0 -map 0:a:0 -af apad -c:v copy -c:a ac3 -ar 48000 -shortest -avoid_negative_ts make_zero -fflags +genpts -f vob -b:v 9M -b:a 192k -y '" + out_vob_path + "'"    #version with only audio pad
#        ffmpeg_vob_copy_string = ffmpeg_command + " -i " + v + " -map 0:v:0 -map 0:a:0 -video_track_timescale 90000 -af apad -c:v copy -c:a ac3 -ar 48000 -shortest -avoid_negative_ts make_zero -fflags +genpts -f vob -b:v 9M -b:a 192k -y '" + out_vob_path + "'"    #version with tbs fix and audio pad
#        run_command(ffmpeg_vob_copy_string)


    ##see if mylist already exists, if so delete it.
#    try:
#        os.remove(first_file_path + ".mylist.txt")
#    except OSError:
#        pass

    #writing list of vobs to concat
#    f = open(first_file_path + ".mylist.txt", "w")
#    for v in input_vobList:
#        v_name = v.split("/")[-1]
#        out_vob_path = first_file_path + ".VOBS/" + v_name
#        f.write("file '" + out_vob_path + "'")
#        f.write("\n")
#    f.close()

    return has_vobs

def transcode_VOBS(first_file_path, transcode_string, output_ext, ffmpeg_command):
    extension = os.path.splitext(first_file_path)[1]
    vob_folder_path = first_file_path + ".VOBS/"
    vob_list = []
    for v in os.listdir(vob_folder_path):
        if not v.startswith('.'):
            if v.endswith('.vob'):
                vob_list.append(first_file_path + ".VOBS/" + v)

    if len(vob_list) == 1:
        output_path = first_file_path.replace(extension,output_ext)
        ffmpeg_vob_concat_string = ffmpeg_command + " -i '" + vob_list[0] + "' " + transcode_string + " '" + output_path + "'"
        print ffmpeg_vob_concat_string
        run_command(ffmpeg_vob_concat_string)
    else:
        inc = 1
        for vob_path in vob_list:
            output_path = first_file_path.replace(extension,"") + "_" + str(inc) + output_ext
            ffmpeg_vob_concat_string = ffmpeg_command + " -i '" + vob_path + "' " + transcode_string + " '" + output_path + "'"
            print ffmpeg_vob_concat_string
            run_command(ffmpeg_vob_concat_string)
            inc += 1

# we're not using this function anymore
#def concatenate_VOBS(first_file_path, transcode_string, output_ext, ffmpeg_command):
#    catList = first_file_path + ".mylist.txt"
#    extension = os.path.splitext(first_file_path)[1]
#    output_path = first_file_path.replace(extension,output_ext)
#    ffmpeg_vob_concat_string = ffmpeg_command + " -vsync 0 -f concat -safe 0 -i '" + catList + "' " + transcode_string + " '" + output_path + "'"
#    print ffmpeg_vob_concat_string
#    run_command(ffmpeg_vob_concat_string)

def run_command(command):
    try:
        run = subprocess.call([command], shell=True)
        return run
    except Exception, e:
        print e
        return e

# Used to make colored text
class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Standard boilerplate to call the main() function to begin
# the program.
if __name__ == '__main__':
    main()

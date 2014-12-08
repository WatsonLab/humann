#!/usr/bin/env python

"""
HUMAnN2 : HMP Unified Metabolic Analysis Network 2

HUMAnN2 is a pipeline for efficiently and accurately determining 
the coverage and abundance of microbial pathways in a community 
from metagenomic data. Sequencing a metagenome typically produces millions 
of short DNA/RNA reads.

Dependencies: MetaPhlAn2, ChocoPhlAn, Bowtie2, Rapsearch2 or Usearch

To Run: ./humann2.py -i <input.fastq> -o <output_dir>

Copyright (c) 2014 Harvard School of Public Health

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
"""

import argparse
import sys
import subprocess
import os
import time
import tempfile
import re
import logging

from src import utilities
from src import prescreen
from src import nucleotide_search
from src import store
from src import translated_search
from src import config
from src import quantify_families
from src import quantify_modules

# name global logging instance
logger=logging.getLogger(__name__)

def parse_arguments (args):
    """ 
    Parse the arguments from the user
    """
    parser = argparse.ArgumentParser(
        description= "HUMAnN2 : HMP Unified Metabolic Analysis Network 2\n",
        formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument(
        "-v","--verbose", 
        help="additional output is printed\n", 
        action="store_true",
        default=config.verbose)
    parser.add_argument(
        "-r","--resume", 
        help="bypass commands if the output files exist\n", 
        action="store_true",
        default=config.resume)
    parser.add_argument(
        "--bypass_prescreen", 
        help="bypass the prescreen step and run on the full ChocoPhlAn database\n", 
        action="store_true",
        default=config.bypass_prescreen)
    parser.add_argument(
        "--bypass_nucleotide_index", 
        help="bypass the nucleotide index step and run on the indexed ChocoPhlAn database\n", 
        action="store_true",
        default=config.bypass_nucleotide_index)
    parser.add_argument(
        "-i", "--input", 
        help="input file of type {" +",".join(config.input_format_choices)+ "} \n[REQUIRED]", 
        metavar="<input.fastq>", 
        required=True)
    parser.add_argument(
        "-o", "--output", 
        help="directory to write output files\n[REQUIRED]", 
        metavar="<output>", 
        required=True)
    parser.add_argument(
        "-c", "--chocophlan",
        help="directory containing the ChocoPhlAn database\n[DEFAULT: " 
            + config.chocophlan + " ]", 
        metavar="<chocophlan>")
    parser.add_argument(
        "-u", "--uniref",
        help="directory containing the UniRef database\n[DEFAULT: " 
            + config.uniref + " ]", 
        metavar="<uniref>")
    parser.add_argument(
        "--metaphlan",
        help="directory containing the MetaPhlAn software\n[DEFAULT: $PATH]", 
        metavar="<metaplhan>")
    parser.add_argument(
        "--o_log", 
        help="log file\n" + 
        "[DEFAULT: temp/sample.log]", 
        metavar="<sample.log>")
    parser.add_argument(
        "--log_level", 
        help="level of messages to display in log\n" + 
        "[DEFAULT: " + config.log_level + " ]", 
        default=config.log_level,
        choices=config.log_level_choices)
    parser.add_argument(
        "--temp", 
        help="keep temp output files\n" + 
            "[DEFAULT: temp files are removed]", 
        action="store_true")
    parser.add_argument(
        "--bowtie2",
        help="directory of the bowtie2 executable\n[DEFAULT: $PATH]", 
        metavar="<bowtie2>")
    parser.add_argument(
        "--threads", 
        help="number of threads/processes\n[DEFAULT: " + str(config.threads) + " ]", 
        metavar="<" + str(config.threads) + ">", 
        type=int,
        default=config.threads) 
    parser.add_argument(
        "--prescreen_threshold", 
        help="minimum percentage of reads matching a species\n[DEFAULT: "
            + str(config.prescreen_threshold) + "]", 
        metavar="<" + str(config.prescreen_threshold) + ">", 
        type=float,
        default=config.prescreen_threshold) 
    parser.add_argument(
        "--identity_threshold", 
        help="identity threshold to use with the translated search\n[DEFAULT: " 
            + str(config.identity_threshold) + "]", 
        metavar="<" + str(config.identity_threshold) + ">", 
        type=float,
        default=config.identity_threshold) 
    parser.add_argument(
        "--usearch", 
        help="directory containing the usearch executable\n[DEFAULT: $PATH]", 
        metavar="<usearch>")
    parser.add_argument(
        "--rapsearch", 
        help="directory containing the rapsearch executable\n[DEFAULT: $PATH]", 
        metavar="<rapsearch>")
    parser.add_argument(
        "--metaphlan_output", 
        help="output file created by metaphlan\n[DEFAULT: file will be created]", 
        metavar="<bugs_list.tsv>")
    parser.add_argument(
        "--translated_alignment", 
        help="software to use for translated alignment\n[DEFAULT: " + 
            config.translated_alignment_selected + "]", 
        default=config.translated_alignment_selected,
        choices=config.translated_alignment_choices)
    parser.add_argument(
        "--xipe",
        help="turn on/off the xipe computation\n[DEFAULT: " +
        config.xipe_toggle + " ]",
        default=config.xipe_toggle,
        choices=config.toggle_choices)
    parser.add_argument(
        "--minpath",
        help="turn on/off the minpath computation\n[DEFAULT: " + 
        config.minpath_toggle + " ]",
        default=config.minpath_toggle,
        choices=config.toggle_choices)
    parser.add_argument(
        "--output_format",
        help="the format of the output files\n[DEFAULT: " +
        config.output_format + " ]",
        default=config.output_format,
        choices=config.output_format_choices)
    parser.add_argument(
        "--input_format",
        help="the format of the input file\n[DEFAULT: format identified by software ]",
        choices=config.input_format_choices)
    parser.add_argument(
        "--pathways_databases",
        help="the two mapping files to use for pathway computations\n[DEFAULT: " +
        config.pathways_database_part1 + " , " + config.pathways_database_part2 + " ]",
        metavar=("<pathways_database_part1.tsv>","<pathways_database_part2.tsv>"),
        nargs=2)

    return parser.parse_args()
	
	 
def update_configuration(args):
    """
    Update the configuration settings based on the arguments
    """
    
    # Use the full path to the input file
    args.input=os.path.abspath(args.input)

    # If set, append paths executable locations
    if args.metaphlan:
        utilities.add_exe_to_path(os.path.abspath(args.metaphlan))    
    
    if args.bowtie2:
        utilities.add_exe_to_path(os.path.abspath(args.bowtie2))
    
    if args.usearch:
        utilities.add_exe_to_path(os.path.abspath(args.usearch))

    if args.rapsearch:
        utilities.add_exe_to_path(os.path.abspath(args.rapsearch))
 
    humann2_fullpath=os.path.dirname(os.path.realpath(__file__)) 
 
    # Set the locations of the pathways databases
    if args.pathways_databases:
        config.pathways_database_part1=args.pathways_databases[0]
        config.pathways_database_part2=args.pathways_databases[1]
        config.pathways_recursion=False
    else:
        # add the full path to the database
        config.pathways_database_part1=os.path.join(humann2_fullpath, 
            config.pathways_database_part1)
        config.pathways_database_part2=os.path.join(humann2_fullpath,
            config.pathways_database_part2)
        
    # Set the locations of the other databases
    if args.chocophlan:
        config.chocophlan=os.path.abspath(args.chocophlan)
    else:
        config.chocophlan=os.path.join(humann2_fullpath,config.chocophlan)
        
    if args.uniref:
        config.uniref=os.path.abspath(args.uniref)
    else:
        config.uniref=os.path.join(humann2_fullpath,config.uniref)

    # if set, update the config run mode to resume
    if args.resume:
        config.resume=True  
            
    # if set, update the config run mode to verbose
    if args.verbose:
        config.verbose=True  
   
    # if set, update the config run mode to bypass prescreen step
    if args.bypass_prescreen:
        config.bypass_prescreen=True  
    
    # if set, update the config run mode to bypass nucleotide index step
    if args.bypass_nucleotide_index:
        config.bypass_nucleotide_index=True  
        config.bypass_prescreen=True  
        
    # Update thresholds
    config.prescreen_threshold=args.prescreen_threshold
    config.identity_threshold=args.identity_threshold
    
    # Update threads
    config.threads=args.threads
    
    # Update translated alignment software
    config.translated_alignment_selected=args.translated_alignment
        
    # Update the computation toggle choices
    config.xipe_toggle=args.xipe
    config.minpath_toggle=args.minpath
        
    # If minpath is set to run, install if not already installed
    if config.minpath_toggle == "on":
        utilities.install_minpath() 
    
    # Check that the input file exists and is readable
    if not os.path.isfile(args.input):
        sys.exit("CRITICAL ERROR: Can not find input file selected: "+ args.input)
        
    if not os.access(args.input, os.R_OK):
        sys.exit("CRITICAL ERROR: Not able to read input file selected: " + args.input)
     
    # Check that the output directory is writeable
    output_dir = os.path.abspath(args.output)
    
    if not os.path.isdir(output_dir):
        try:
            print("Creating output directory: " + output_dir)
            os.mkdir(output_dir)
        except EnvironmentError:
            sys.exit("CRITICAL ERROR: Unable to create output directory.")
    
    if not os.access(output_dir, os.W_OK):
        sys.exit("CRITICAL ERROR: The output directory is not " + 
            "writeable. This software needs to write files to this directory.\n" +
            "Please select another directory.")
        
    print("Output files will be written to: " + output_dir) 

    # Set the basename of the temp files to the sample name
    config.file_basename=os.path.basename(args.input).split('.')[0]
    
    # Set the output format
    config.output_format=args.output_format
    
    # Set final output file names and location
    config.pathabundance_file=os.path.join(output_dir,
            config.file_basename + config.pathabundance_file + "." + 
            config.output_format)
    config.pathcoverage_file=os.path.join(output_dir,
            config.file_basename + config.pathcoverage_file + "." + 
            config.output_format)
    config.genefamilies_file=os.path.join(output_dir,
            config.file_basename + config.genefamilies_file + "." + 
            config.output_format)

    # set the location of the temp directory
    if args.temp:
        config.temp_dir=os.path.join(output_dir,config.file_basename+"_HUMAnN2_temp")
        if not os.path.isdir(config.temp_dir):
            try:
                os.mkdir(config.temp_dir)
            except EnvironmentError:
                sys.exit("Unable to create temp directory: " + config.temp_dir)
    else:
        config.temp_dir=tempfile.mkdtemp( 
            prefix=config.file_basename+'_HUMAnN2_temp_',dir=output_dir)
        
    # create the unnamed temp directory
    config.unnamed_temp_dir=tempfile.mkdtemp(dir=config.temp_dir)
    
    message="Writing temp files to directory: " + config.temp_dir
    logger.info(message)
    if config.verbose: 
        print("\n"+message+"\n")

    # set the name of the log file 
    log_file=os.path.join(config.temp_dir,config.file_basename+".log")
    
    # change file name if set
    if args.o_log:
        log_file=args.o_log
        
    # configure the logger
    logging.basicConfig(filename=log_file,format='%(asctime)s - %(name)s - %(levelname)s: %(message)s',
        level=getattr(logging,args.log_level), filemode='w', datefmt='%m/%d/%Y %I:%M:%S %p')
    
     
def check_requirements(args):
    """
    Check requirements (file format, dependencies, permissions)
    """

    # Check the pathways database files exist and are readable
    utilities.file_exists_readable(config.pathways_database_part1)
    utilities.file_exists_readable(config.pathways_database_part2)

    # Determine the input file format if not provided
    if not args.input_format:
        args.input_format=utilities.determine_file_format(args.input)
        
        if args.input_format == "unknown":
            sys.exit("CRITICAL ERROR: Unable to determine the input file format." +
                " Please provide the format with the --input_format argument.")
        
    # If the input file is compressed, then decompress
    if args.input_format.endswith(".gz"):
        new_file=utilities.gunzip_file(args.input)
        
        if new_file:
            args.input=new_file
            args.input_format=args.input_format.split(".")[0]
        else:
            sys.exit("CRITICAL ERROR: Unable to use gzipped input file. " + 
                " Please check the format of the input file.")
            
    # If the biom output format is selected, check for the biom package
    if config.output_format=="biom":
        if not utilities.find_exe_in_path("biom"):
            sys.exit("CRITICAL ERROR: The biom executable can not be found. "
            "Please check the install or select another output format.")
     
    # If the file is fasta/fastq check for requirements   
    if args.input_format in ["fasta","fastq"]:
        # Check that the chocophlan directory exists
        if not config.bypass_nucleotide_index:
            if not os.path.isdir(config.chocophlan):
                if args.chocophlan:
                    sys.exit("CRITICAL ERROR: The directory provided for the ChocoPhlAn database at " 
                        + args.chocophlan + " does not exist. Please select another directory.")
                else:
                    sys.exit("CRITICAL ERROR: The default ChocoPhlAn database directory of "
                        + config.chocophlan + " does not exist. Please provide the location "
                        + "of the ChocoPhlAn directory using the --chocophlan option.")	
    
        # Check that the files in the chocophlan folder are of the right format
        if not config.bypass_nucleotide_index:
            valid_format_count=0
            for file in os.listdir(config.chocophlan):
                # expect most of the file names to be of the format g__*s__*
                if re.search("^[g__][s__]",file): 
                    valid_format_count+=1
            if valid_format_count == 0:
                sys.exit("CRITICAL ERROR: The directory provided for ChocoPhlAn does not "
                    + "contain files of the expected format (ie \'^[g__][s__]\').")
                
        # Check that the metaphlan2 executable can be found
        if not config.bypass_prescreen and not config.bypass_nucleotide_index:
            if not utilities.find_exe_in_path("metaphlan2.py"): 
                sys.exit("CRITICAL ERROR: The metaphlan2.py executable can not be found. "  
                    "Please check the install.")

        # Check that the bowtie2 executable can be found
        if not utilities.find_exe_in_path("bowtie2"): 
            sys.exit("CRITICAL ERROR: The bowtie2 executable can not be found. "  
                "Please check the install.")
 
        if not config.bypass_translated_search:
            # Check that the uniref directory exists
            if not os.path.isdir(config.uniref):
                if args.uniref:
                    sys.exit("CRITICAL ERROR: The directory provided for the UniRef database at " 
                        + args.uniref + " does not exist. Please select another directory.")
                else:
                    sys.exit("CRITICAL ERROR: The default UniRef database directory of "
                        + config.uniref + " does not exist. Please provide the location "
                        + "of the UniRef directory using the --uniref option.")            	
    
            # Check that all files in the uniref folder are of *.udb extension or fasta
            # if translated search selected is usearch
            if config.translated_alignment_selected == "usearch":
                for file in os.listdir(config.uniref):
                    if not file.endswith(config.usearch_database_extension):
                        if utilities.fasta_or_fastq(os.path.join(config.uniref,file)) != "fasta":
                            sys.exit("CRITICAL ERROR: The directory provided for the UniRef database "
                                + "at " + config.uniref + " "
                                + "contains files of an unexpected format. Only files of the"
                                + " udb or fasta format are allowed.") 
    
            # Check that some of the database files are of the *.info extension
            valid_format_count=0
            if config.translated_alignment_selected == "rapsearch":
                for file in os.listdir(config.uniref):
                    if file.endswith(config.rapsearch_database_extension):
                        valid_format_count+=1
                if valid_format_count == 0:
                    sys.exit("CRITICAL ERROR: The UniRef directory provided at " + config.uniref 
                        + " has not been formatted to run with"
                        " the rapsearch translated alignment software. Please format these files.")

            # Check for correct usearch version
            if config.translated_alignment_selected == "usearch":
                utilities.check_software_version("usearch","-version",config.usearch_version)
        
            # Check that the translated alignment executable can be found
            if not utilities.find_exe_in_path(config.translated_alignment_selected):
                sys.exit("CRITICAL ERROR: The " +  config.translated_alignment_selected + 
                    " executable can not be found. Please check the install.")
        
        
def main():
    # Parse arguments from command line
    args=parse_arguments(sys.argv)
    
    # Update the configuration settings based on the arguments
    update_configuration(args)
    
    # Check for required files, software, databases, and also permissions
    check_requirements(args)

    # Initialize alignments and gene scores
    alignments=store.Alignments()
    gene_scores=store.GeneScores()
    
    # Load in the reactions database
    reactions_database=store.ReactionsDatabase(config.pathways_database_part1)

    message="Load pathways database part 1: " + config.pathways_database_part1
    logger.info(message)
    if config.verbose:
        print(message)
    
    # Load in the pathways database
    pathways_database=store.PathwaysDatabase(config.pathways_database_part2, 
        config.pathways_recursion)
    
    message="Load pathways database part 2: " + config.pathways_database_part2
    logger.info(message)
    if config.verbose:
        print(message)

    # Start timer
    start_time=time.time()

    # Process fasta or fastq input files
    if args.input_format in ["fasta","fastq"]:
        # Run prescreen to identify bugs
        bug_file = "Empty"
        if args.metaphlan_output:
            bug_file = args.metaphlan_output
        else:
            if not config.bypass_prescreen:
                bug_file = prescreen.alignment(args.input)
    
        message=str(int(time.time() - start_time)) + " seconds from start"
        logger.info(message)
        if config.verbose:
            print(message)
    
        # Create the custom database from the bugs list
        custom_database = ""
        if not config.bypass_nucleotide_index:
            custom_database = prescreen.create_custom_database(config.chocophlan, bug_file)
        else:
            custom_database = "Bypass"
    
        message=str(int(time.time() - start_time)) + " seconds from start"
        logger.info(message)
        if config.verbose:
            print(message)
    
        # Run nucleotide search on custom database
        if custom_database != "Empty":
            if not config.bypass_nucleotide_index:
                nucleotide_index_file = nucleotide_search.index(custom_database)
            else:
                nucleotide_index_file = config.chocophlan
            nucleotide_alignment_file = nucleotide_search.alignment(args.input, 
                nucleotide_index_file)
    
            message=str(int(time.time() - start_time)) + " seconds from start"
            logger.info(message)
            if config.verbose:
                print(message)
    
            # Determine which reads are unaligned and reduce aligned reads file
            # Remove the alignment_file as we only need the reduced aligned reads file
            [ unaligned_reads_file_fasta, unaligned_reads_store, reduced_aligned_reads_file ] = nucleotide_search.unaligned_reads(
                nucleotide_alignment_file, alignments)
    
            # Print out total alignments per bug
            message="Total bugs from nucleotide alignment: " + str(alignments.count_bugs())
            logger.info(message)
            print(message)
            
            message=alignments.counts_by_bug()
            logger.info("\n"+message)
            print(message)        
    
            message="Total gene families from nucleotide alignment: " + str(alignments.count_genes())
            logger.info(message)
            print("\n"+message)
    
            # Report reads unaligned
            message="Estimate of unaligned reads: " + utilities.estimate_unaligned_reads(
                args.input, unaligned_reads_file_fasta) + "%"
            logger.info(message)
            print("\n"+message+"\n")  
        else:
            logger.debug("Custom database is empty")
            reduced_aligned_reads_file = "Empty"
            unaligned_reads_file_fasta=args.input
            unaligned_reads_store=store.Reads(unaligned_reads_file_fasta)
    
        # Do not run if set to bypass translated search in config file
        if not config.bypass_translated_search:
            # Run translated search on UniRef database if unaligned reads exit
            if unaligned_reads_store.count_reads()>0:
                translated_alignment_file = translated_search.alignment(config.uniref, 
                    unaligned_reads_file_fasta)
        
                if config.verbose:
                    print(str(int(time.time() - start_time)) + " seconds from start")
        
                # Determine which reads are unaligned
                translated_unaligned_reads_file_fastq = translated_search.unaligned_reads(
                    unaligned_reads_store, translated_alignment_file, alignments)
        
                # Print out total alignments per bug
                message="Total bugs after translated alignment: " + str(alignments.count_bugs())
                logger.info(message)
                print(message)
            
                message=alignments.counts_by_bug()
                logger.info("\n"+message)
                print(message)
        
                message="Total gene families after translated alignment: " + str(alignments.count_genes())
                logger.info(message)
                print("\n"+message)
        
                # Report reads unaligned
                message="Estimate of unaligned reads: " + utilities.estimate_unaligned_reads(
                    args.input, translated_unaligned_reads_file_fastq) + "%"
                logger.info(message)
                print("\n"+message+"\n")  
            else:
                message="All reads are aligned so translated alignment will not be run"
                logger.info(message)
                print(message)
        else:
            message="Bypass translated search"
            logger.info(message)
            print(message)
    
    # Process input files of sam format
    elif args.input_format in ["sam"]:
        # Store the sam mapping results
        [unaligned_reads_file_fasta, unaligned_reads_store, 
            reduced_aligned_reads_file] = nucleotide_search.unaligned_reads(
            args.input, alignments, keep_sam=True)
            
    # Process input files of tab-delimited blast format
    elif args.input_format in ["blastm8"]:
        # Create new unaligned reads store
        unaligned_reads_store=store.Reads()
        
        # Store the blastm8 mapping results
        translated_unaligned_reads_file_fastq = translated_search.unaligned_reads(
            unaligned_reads_store, args.input, alignments)
        
    # Handle input files of unknown formats
    else:
        sys.exit("CRITICAL ERROR: Input file of unknown format.")

    # Compute the gene families
    message="Computing gene families ..."
    logger.info(message)
    print("\n"+message)
    
    families_file=quantify_families.gene_families(alignments,gene_scores)

    message=str(int(time.time() - start_time)) + " seconds from start"
    logger.info(message)
    if config.verbose:
        print(message)
    
    # Identify reactions and then pathways from the alignments
    message="Computing pathways abundance and coverage ..."
    logger.info(message)
    print("\n"+message)
    pathways_and_reactions_store=quantify_modules.identify_reactions_and_pathways(
        gene_scores, reactions_database, pathways_database)

    # Compute pathway abundance and coverage
    abundance_file, coverage_file=quantify_modules.compute_pathways_abundance_and_coverage(
        pathways_and_reactions_store, pathways_database)

    message=str(int(time.time() - start_time)) + " seconds from start"
    logger.info(message)
    if config.verbose:
        print(message)

    output_files=[families_file,abundance_file,coverage_file]
    message="\nOutput files created: \n" + "\n".join(output_files) + "\n"
    logger.info(message)
    print(message)

    # Remove the unnamed temp files
    utilities.remove_directory(config.unnamed_temp_dir)

    # Remove named temp directory
    if not args.temp:
        utilities.remove_directory(config.temp_dir)
        

if __name__ == "__main__":
	main()

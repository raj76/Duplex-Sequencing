'''
##########################################################################################################################
##########################################################################################################################
##							Consensus Maker							##
##							  Version 2.2							##
##					      By Brendan Kohrn and Scott Kennedy(1)					##
##		(1) Department of Pathology, University of Washington School of Medicine, Seattle, WA 98195		##
##							August 29, 2013							##
##########################################################################################################################
##########################################################################################################################
##															##
##					   	    Written for Python 2.7.3						##
##					       Required modules: Pysam, Samtools					##
##															##
##	This program is intended to be run on a paired-end BAM file, sorted by read position, with duplex tags in the 	##
##header and constant read length.  It will output a paired-end BAM file with single strand consensus sequences 	##
##(SSCSs), and a .tagcounts file which contains the different tags (on both strands) and how many times they occur, 	##
##even if they are not used in SSCS generation, in order by read.  In addition, it will output a BAM file of SSCSs 	##
##which are unpaired, either because one of the pair didn't match the criteria for allignment, or because of some other ##
##reason, and a BAM file of all unconsidered sequences in the original file.  Quality scores on the output BAM files are meaningless.  The file produced by this program ##
##is meant to be realigned to the reference genome afterwards.								##
##															##
##	The program starts at the position of the first good read (A good read is mapped in a propper pair, the two 	##
##reads don't overlap, and the barcode is non-repetitive.)  It then goes through the file until it finds a new 	##
##position, saving all reads as it goes.  When it finds a new position, it sends the saved reads to the consensus 	##
##maker, one tag at a time, untill it runs out of tags.  Consensus sequences are saved until their mates come up, at 	##
##which point both are written to the output BAM file, first read first.  After emptying the reads from the first 	##
##position, it continues on through the origional file until it finds another new position, sends those reads to the 	##
##consensus maker, and so on until the end of the file.  At the end of the file, any remaining reads are sent through 	##
##the consensus maker, and any unpaired consensuses are written to extraConsensus.bam.  				##
##															##
##In the future, the program may be able to autodetect read length.							##
##															##
##########################################################################################################################
##########################################################################################################################
##															##
##To use, imput:  													##
##															##
##python consensusMaker2.1.py --infile <inBamFile.bam> --tagFile  <outTagFile.tagcounts> --outfile <outBamFile.bam> --minmem <minMem> --maxmem <maxMem> --cutoff <cutoffPercent> --Ncutoff <Ncutoff> --readlength <readLength> 								      ##
##															##
##and replace <> with parameters.  -p is optional.												##
##															##
##########################################################################################################################
##########################################################################################################################
'''

'''
ChangeLog in this version:
Inserted try in consensusMaker.  
Added cigarDictionary as readDict[6]
Added cigar string comparison before sending to consensus maker.
'''

import sys
import pysam
import re
from collections import defaultdict
from argparse import ArgumentParser

##########################################################################################################################
#Parameters to be input.												 #
##########################################################################################################################

parser=ArgumentParser()
parser.add_argument("--infile", action="store", dest="infile", help="input BAM file", default='sys.stdin')
parser.add_argument("--tagfile",  action="store",  dest="tagfile", help="output tagcounts file",  default='sys.stdout')
parser.add_argument("--outfile",  action="store", dest="outfile", help="output BAM file",  default='sys.stdout')
parser.add_argument("--rep_filt", action="store",  type=int, dest='rep_filt', help="Remove tags with homomeric runs of nucleotides of length x", default=9 )
parser.add_argument('--minmem', type=int, default=0, dest='minmem', help="Minimum number of reads allowed to comprise a consensus.")
parser.add_argument('--maxmem', type=int, default=100, dest='maxmem', help="Maximum number of reads allowed to comprise a consensus.")
parser.add_argument('--cutoff', type=float, default=0, dest='cutoff', help="Percentage of nucleotides at a given position in a read that must be identical in order for a consensus to be called at that position.")
parser.add_argument('--Ncutoff', type=float, default=1, dest='Ncutoff', help="Maximum percentage of Ns allowed in a consensus")
parser.add_argument('--readlength', type=int, default=81, dest='read_length', help="Length of the input read that is being used.")
parser.add_argument('--read_type', type=str,  action="store", default="dual_map", help="Type of read.  Options: dual_map: both reads map properly.  Doesn't consider read pairs where only one read maps.  mono_map: considers any read pair where one read maps.  hairpin: only use for hairpin sequence.")
o = parser.parse_args()

##########################################################################################################################
#Consensus Maker module.  Takes a list of sequences, and finds a consensus by simple majority.  			 #
##########################################################################################################################

def printRead(readIn):
	sys.stderr.write(str(readIn.qname) +  "	" + str(readIn.flag) + "	" + str(readIn.tid) + "	" + str(readIn.pos) + "	" + str(readIn.mapq) + "	" + str(readIn.cigar) + "	" + str(readIn.mrnm) + "	" + str(readIn.mpos) + "	" + str(readIn.isize) + "	" + str(readIn.seq) + "	" + str(readIn.qual) + "	" + str(readIn.tags) + "\n")

def consensusMaker (groupedReadsList,  cutoff,  readLength) :
	'''The consensus maker uses a simple "majority rules" algorithm to qmake a consensus at each base position.  If no nucleotide majority reaches above the minimum theshold (--cutoff), the position is considered undefined and an 'N' is placed at that position in the read.'''
	nucIdentityList=[0, 0, 0, 0, 0, 0] # In the order of T, C, G, A, N, Total
	nucKeyDict = {0:'T', 1:'C', 2:'G', 3:'A', 4:'N'}
	seqDict = {}
	consensusRead = ''
	
	for i in xrange(readLength) : #Count the types of nucleotides at a position in a read. i is the nucleotide index within a read in groupedReadsList
		for j in xrange(len(groupedReadsList)): #Do this for every read that comprises a SMI group. j is the read index within groupedReadsList
			try:
				if groupedReadsList[j][i] == 'T' :
					nucIdentityList[0] += 1
					nucIdentityList[5] += 1
				elif groupedReadsList[j][i] == 'C':
					nucIdentityList[1] += 1
					nucIdentityList[5] += 1
				elif groupedReadsList[j][i] == 'G':
					nucIdentityList[2] += 1
					nucIdentityList[5] += 1 
				elif groupedReadsList[j][i] == 'A':
					nucIdentityList[3] += 1
					nucIdentityList[5] += 1
				elif groupedReadsList[j][i] == 'N':
					nucIdentityList[4] += 1
					nucIdentityList[5] += 1	
				seqDict[i] = nucIdentityList
				
			except:
				seqDict[i] = nucIdentityList
				nucIdentityList=[0, 0, 0, 0, 0, 0]
				break
		nucIdentityList=[0, 0, 0, 0, 0, 0] #reset for the next nucleotide position

	for i in xrange(readLength) :#rebuild consensus read taking into account the cutoff percentage
		try:
			for j in [0, 1, 2, 3, 4] :
				if float(seqDict[i][j])/float(seqDict[i][5]) > cutoff :
					consensusRead += nucKeyDict[j]
					break
				elif j==4:
					consensusRead += 'N'
		except:
			consensusRead += 'N'
	return consensusRead

##########################################################################################################################
#Initialization of all global variables, main input/output files, and main iterator and dictionaries.  			 #
##########################################################################################################################
goodFlag=[]
if o.read_type == "hairpin":
	goodFlag=[161,81,145,97]
elif o.read_type == "dual_map":
	goodFlag=[83, 99, 147, 163]
elif o.read_type == "mono_map":
	goodFlag=[153, 89, 117, 181, 83, 99, 171, 163]

inBam = pysam.Samfile( o.infile, "rb" ) #open the input BAM file
outBam = pysam.Samfile( o.outfile, "wb", template = inBam ) #open the output BAM file
outNC1 = pysam.Samfile( o.outfile.replace(".bam","_LCC.bam"),"wb", template = inBam )
nonMap = pysam.Samfile( o.outfile.replace(".bam","_NM.bam"), "wb", template = inBam ) #file for reads with strange flags
#outStd = pysam.Samfile('-', 'wb', template = inBam ) #open the stdOut writer


readNum=0

fileDone=False #initialize end of file bool
finished=False
readOne=False

qualScore = 'i'*o.read_length #set a dummy quality score

bamEntry = inBam.fetch( until_eof = True ) #initialize the iterator
firstRead = bamEntry.next() #get the first read

firstTag=''
readDict = {} #initialize the read dictionary
tagDict = defaultdict( lambda: 0 ) #initialize the tag dictionary

##########################################################################################################################
#Find the first good read to serve as a start point for analysis.    							 #
##########################################################################################################################

while readOne==False:
	readNum +=1
	overlap=False
	if readNum % 100000 == 0:
		sys.stderr.write("Reads processed:" + str(readNum) + "\n")
	if firstRead.pos < firstRead.mpos and firstRead.mpos < firstRead.pos + o.read_length and int( firstRead.flag ) in ( 83, 99, 147, 163):
		overlap=True
	elif firstRead.pos > firstRead.mpos and firstRead.pos < firstRead.mpos + o.read_length and int( firstRead.flag ) in ( 83, 99, 147, 163):
		overlap=True
	elif firstRead.pos==firstRead.mpos and int( firstRead.flag ) in ( 83, 99, 147, 163):
		overlap=True

	try:
		tag = firstRead	.qname.split('#')[1] + (":1" if firstRead.is_read1 == True else (":2" if firstRead.is_read2 == True else ":se")) #extract the barcode
		tagDict[tag]+=1
	except:
		exit()
	
	if int( firstRead.flag ) in goodFlag  and overlap==False: #check if the given read is good data
		
	  	if ('A'*o.rep_filt in tag) or ('C'*o.rep_filt in tag) or ('G'*o.rep_filt in tag) or ('C'*o.rep_filt in tag) : 	
			#check for bad barcodes
			pass 
		else :
			#Found a good line
			firstTag=tag
			readOne=True
			tagDict[firstTag] -= 1
	else:
		nonMap.write(firstRead)
		if fileDone==False:
			try: #keep StopIteration error from happening
				firstRead = bamEntry.next() #iterate the line

			except:
				fileDone = True #tell the program that it has reached the end of the file
		else:
			#Oops...no good reads!
			sys.stderr.write("Oops!  There are no good reads in this BAM file!  Sorry!\n")
			finished=True
			readOne=True

consensusDict={}

cigDum = firstRead.cigar #set a dummy cigar score

##########################################################################################################################
#Start going through the input BAM file, one position at a time.    							 #
##########################################################################################################################
for line in bamEntry:
	#reinitialize first line
	if readOne==True:
		#firstCig = {firstRead.cigar:[1,firstRead.seq]}
		readDict[firstTag] = [firstRead.flag, firstRead.rname, firstRead.pos, firstRead.mrnm, firstRead.mpos, firstRead.isize, {str(firstRead.cigar): [1,firstRead.cigar,firstRead.seq]}]
		tagDict[firstTag] += 1
		readOne=False
	while line.pos == firstRead.pos and fileDone==False:
		if readNum % 100000 == 0:
			sys.stderr.write("Reads processed:" + str(readNum) + "\n")
		lineFlag = 0
		overlap=False
		if line.pos < line.mpos and line.mpos < line.pos + o.read_length and int( firstRead.flag ) in ( 83, 99, 147, 163):
			overlap=True
		elif line.pos > line.mpos and line.pos < line.mpos + o.read_length and int( firstRead.flag ) in ( 83, 99, 147, 163):
			overlap=True
		elif line.pos==line.mpos and int( firstRead.flag ) in ( 83, 99, 147, 163):
			overlap=True
		readNum +=1
		
		tag = line.qname.split('#')[1] + (":1" if line.is_read1 == True else (":2" if line.is_read2 == True else ":se"))
		tagDict[tag] += 1
		
		if int( line.flag ) in goodFlag and overlap==False: #check if the given read is good data
			if ('A'*o.rep_filt in tag) or ('C'*o.rep_filt in tag) or ('G'*o.rep_filt in tag) or ('C'*o.rep_filt in tag) : 
				#check for bad barcodes
				pass 
			else :
				#add the sequence to the read dictionary
				if tag not in readDict:
					readDict[tag] = [line.flag, line.rname, line.pos, line.mrnm, line.mpos, line.isize,{str(line.cigar):[0,line.cigar]}]

				if str(line.cigar) not in readDict[tag][6]:
					readDict[tag][6][str(line.cigar)]=[0,line.cigar]
				readDict[tag][6][str(line.cigar)].append(line.seq)
				readDict[tag][6][str(line.cigar)][0]+=1
		else:
			nonMap.write(line)
		try: #keep StopIteration error from happening
			line = bamEntry.next() #iterate the line
		except:
			fileDone = True #tell the program that it has reached the end of the file

	else:

##########################################################################################################################
#Send reads to consensusMaker												 #
##########################################################################################################################
		
		
		firstRead = line #store the present line for the next group of lines
		firstTag = firstRead.qname.split('#')[1] + (":1" if firstRead.is_read1 == True else (":2" if firstRead.is_read2 == True else ":se"))
		readOne=True
		for dictTag in readDict.keys(): #extract sequences to send to the consensus maker
			
			
			cigComp={}
			for cigStr in readDict[dictTag][6].keys(): #determin the most common cigar string
				cigComp[cigStr]=readDict[dictTag][6][cigStr][0]
			maxCig=max(cigComp)

			
			if cigComp[maxCig] <= o.maxmem and cigComp[maxCig] >= o.minmem:
				consensus = consensusMaker( readDict[dictTag][6][maxCig][2:],  o.cutoff,  o.read_length )
				
				for cigStr in readDict[dictTag][6].keys():
					if cigStr != maxCig:
						a = pysam.AlignedRead()
						a.qname = dictTag.split(':')[0]
						a.flag = readDict[dictTag][0]
						a.seq = consensus
						a.rname = readDict[dictTag][1]
						a.pos = readDict[dictTag][2]
						a.mapq = 255
						a.cigar = readDict[dictTag][6][maxCig][1]
						a.mrnm = readDict[dictTag][3]
						a.mpos=readDict[dictTag][4]
						a.isize = readDict[dictTag][5]
						a.qual = qualScore	
						outNC1.write(a)
				cigComp={}
				
				#Filter out consensuses with too many Ns in them
				if consensus.count("N" )/ len(consensus) < o.Ncutoff:
					if len(consensus) < o.read_length :
						print consensus, dictTag.split(':')[0]
					#write a line to the consensusDictionary
					a = pysam.AlignedRead()
					a.qname = dictTag.split(':')[0]
					a.flag = readDict[dictTag][0]
					a.seq = consensus
					a.rname = readDict[dictTag][1]
					a.pos = readDict[dictTag][2]
					a.mapq = 255
					a.cigar = readDict[dictTag][6][maxCig][1]
					a.mrnm = readDict[dictTag][3]
					a.mpos=readDict[dictTag][4]
					a.isize = readDict[dictTag][5]
					a.qual = qualScore
				
##########################################################################################################################
#Write SSCSs to output BAM file in read pairs.			    							 #
##########################################################################################################################
					
					altTag=dictTag.replace(("1" if "1" in dictTag else "2"),("2" if "1" in dictTag else "1"))
					
					if altTag in consensusDict:
						if a.is_read1 == True:
							#if o.pipe==True:
							#	outStd.write(a)
							#	outStd.write(consensusDict[dictTag])
							outBam.write(a)
							outBam.write(consensusDict.pop(altTag))
						else:
							#if o.pipe==True:
							#       outStd.write(consensusDict[dictTag])
							#       outStd.write(a)
							outBam.write(consensusDict.pop(altTag))
							outBam.write(a)
					else:
						consensusDict[dictTag]=a

	readDict={} #reset the read dictionary

##########################################################################################################################
#Write unpaired SSCSs to extraConsensus.bam			     							 #
##########################################################################################################################

extraBam=pysam.Samfile(o.outfile.replace(".bam","_UP.bam"), "wb", template = inBam)
#close BAM files
inBam.close()
outBam.close()
nonMap.close()
outNC1.close()

for consTag in consensusDict.keys():
	extraBam.write(consensusDict.pop(consTag))
extraBam.close()
#outStd.close()
##########################################################################################################################
#Write the tag counts file.					    							 #
##########################################################################################################################

sys.stderr.write("Reads processed:" + str(readNum) + "\n")

tagFile = open( o.tagfile, "w" )
tagFile.write ( "\n".join( [ "%s\t%d" % ( SMI, tagDict[SMI] ) for SMI in sorted( tagDict.keys(), key=lambda x: tagDict[x], reverse=True ) ] ))
tagFile.close()
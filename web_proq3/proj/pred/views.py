# ChangeLog

import os, sys
import tempfile
import re
import subprocess
from datetime import datetime
import time
import math
import shutil

os.environ['TZ'] = 'Europe/Stockholm'
time.tzset()

from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.views.decorators.csrf import csrf_exempt  

# for user authentication
from django.contrib.auth import authenticate, login, logout

# import variables from settings
from django.conf import settings

# global parameters
BASEURL = "/pred/";
MAXSIZE_UPLOAD_MODELFILE_IN_MB = 10
MAXSIZE_UPLOAD_SEQFILE_IN_MB = 0.15
MAXSIZE_UPLOAD_MODELFILE_IN_BYTE = MAXSIZE_UPLOAD_MODELFILE_IN_MB * 1024*1024
MAXSIZE_UPLOAD_SEQFILE_IN_BYTE = MAXSIZE_UPLOAD_SEQFILE_IN_MB * 1024*1024
MAX_DAYS_TO_SHOW = 30
BIG_NUMBER = 100000
MAX_NUMSEQ_FOR_FORCE_RUN = 100
SITE_ROOT = os.path.dirname(os.path.realpath(__file__))
progname =  os.path.basename(__file__)
path_app = "%s/app"%(SITE_ROOT)
sys.path.append(path_app)
path_log = "%s/static/log"%(SITE_ROOT)
gen_logfile = "%s/static/log/%s.log"%(SITE_ROOT, progname)
MAX_ALLOWD_NUMMODEL = 5
path_result = "%s/static/result"%(SITE_ROOT)

suq_basedir = "/tmp"
if os.path.exists("/scratch"):
    suq_basedir = "/scratch"
elif os.path.exists("/tmp"):
    suq_basedir = "/tmp"
suq_exec = "/usr/bin/suq";

python_exec = os.path.realpath("%s/../../env/bin/python"%(SITE_ROOT))


import myfunc

rundir = SITE_ROOT

qd_fe_scriptfile = "%s/qd_boctopus2_fe.py"%(path_app)
gen_errfile = "%s/static/log/%s.err"%(SITE_ROOT, progname)

# Create your views here.
from django.shortcuts import render
from django.http import HttpResponse
from django.http import HttpRequest
from django.http import HttpResponseRedirect
from django.views.static import serve


#from pred.models import Query
from pred.models import SubmissionForm
from pred.models import FieldContainer
from django.template import Context, loader

def index(request):#{{{
    path_tmp = "%s/static/tmp"%(SITE_ROOT)
    path_md5 = "%s/static/md5"%(SITE_ROOT)
    if not os.path.exists(path_result):
        os.mkdir(path_result, 0755)
    if not os.path.exists(path_result):
        os.mkdir(path_tmp, 0755)
    if not os.path.exists(path_md5):
        os.mkdir(path_md5, 0755)
    base_www_url_file = "%s/static/log/base_www_url.txt"%(SITE_ROOT)
    if not os.path.exists(base_www_url_file):
        base_www_url = "http://" + request.META['HTTP_HOST']
        myfunc.WriteFile(base_www_url, base_www_url_file, "w", True)
    return submit_seq(request)
#}}}
def SetColorStatus(status):#{{{
    if status == "Finished":
        return "green"
    elif status == "Failed":
        return "red"
    elif status == "Running":
        return "blue"
    else:
        return "black"
#}}}
def ReadFinishedJobLog(infile, status=""):#{{{
    dt = {}
    if not os.path.exists(infile):
        return dt

    hdl = myfunc.ReadLineByBlock(infile)
    if not hdl.failure:
        lines = hdl.readlines()
        while lines != None:
            for line in lines:
                if not line or line[0] == "#":
                    continue
                strs = line.split("\t")
                if len(strs)>= 10:
                    jobid = strs[0]
                    status_this_job = strs[1]
                    if status == "" or status == status_this_job:
                        jobname = strs[2]
                        ip = strs[3]
                        email = strs[4]
                        try:
                            numseq = int(strs[5])
                        except:
                            numseq = 1
                        method_submission = strs[6]
                        submit_date_str = strs[7]
                        start_date_str = strs[8]
                        finish_date_str = strs[9]
                        dt[jobid] = [status_this_job, jobname, ip, email,
                                numseq, method_submission, submit_date_str,
                                start_date_str, finish_date_str]
            lines = hdl.readlines()
        hdl.close()

    return dt
#}}}
def submit_seq(request):#{{{
    info = {}

    username = request.user.username
    client_ip = request.META['REMOTE_ADDR']
    if username in settings.SUPER_USER_LIST:
        isSuperUser = True
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "submitted_seq.log")
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "finished_job.log")
    else:
        isSuperUser = False
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_submitted_seq.log"%(client_ip))
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_finished_job.log"%(client_ip))

    info['username'] = username
    info['isSuperUser'] = isSuperUser
    info['client_ip'] = client_ip

    # if this is a POST request we need to process the form data
    if request.method == 'POST':
        # create a form instance and populate it with data from the request:
        form = SubmissionForm(request.POST)
        # check whether it's valid:
        if form.is_valid():
            # process the data in form.cleaned_data as required
            # redirect to a new URL:

            jobname = request.POST['jobname']
            email = request.POST['email']
            try:
                targetlength = int(request.POST['targetlength'])
            except ValueError:
                targetlength = None

            rawseq = request.POST['rawseq'] + "\n" # force add a new line
            rawmodel = request.POST['rawmodel'].replace('\r','') + "\n" # force add a new line
            isForceRun = False
            isKeepFiles = False

            if 'forcerun' in request.POST:
                isForceRun = True

            if 'keepfile' in request.POST:
                isKeepFiles = True

            try:
                seqfile = request.FILES['seqfile']
            except KeyError, MultiValueDictKeyError:
                seqfile = ""
            try:
                modelfile = request.FILES['modelfile']
            except KeyError, MultiValueDictKeyError:
                modelfile = ""
            date = time.strftime("%Y-%m-%d %H:%M:%S")
            query = {}
            query['rawseq'] = rawseq
            query['rawmodel'] = rawmodel
            query['seqfile'] = seqfile
            query['modelfile'] = modelfile
            query['targetlength'] = targetlength
            query['email'] = email
            query['jobname'] = jobname
            query['date'] = date
            query['client_ip'] = client_ip
            query['errinfo'] = ""
            query['method_submission'] = "web"
            query['isForceRun'] = isForceRun
            query['username'] = username
            query['isKeepFiles'] = isKeepFiles

            is_valid = ValidateQuery(request, query)

            if is_valid:
                jobid = RunQuery(request, query)

                # type of method_submission can be web or wsdl
                #date, jobid, IP, numseq, size, jobname, email, method_submission
                log_record = "%s\t%s\t%s\t%s\t%d\t%s\t%s\t%s\n"%(query['date'], jobid,
                        query['client_ip'], query['nummodel'],
                        len(query['rawmodel']),query['jobname'], query['email'],
                        query['method_submission'])
                main_logfile_query = "%s/%s/%s"%(SITE_ROOT, "static/log", "submitted_seq.log")
                myfunc.WriteFile(log_record, main_logfile_query, "a")

                divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                        "static/log/divided", "%s_submitted_seq.log"%(client_ip))
                divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                        "static/log/divided", "%s_finished_job.log"%(client_ip))
                if client_ip != "":
                    myfunc.WriteFile(log_record, divided_logfile_query, "a")


                file_seq_warning = "%s/%s/%s/%s"%(SITE_ROOT, "static/result", jobid, "query.warn.txt")
                query['file_seq_warning'] = os.path.basename(file_seq_warning)
                if query['warninfo'] != "":
                    myfunc.WriteFile(query['warninfo'], file_seq_warning, "a")

                query['jobid'] = jobid
                query['raw_query_seqfile'] = "query.raw.fa"
                query['BASEURL'] = BASEURL

                # start the qd_fe if not, in the background
#                 cmd = [qd_fe_scriptfile]
                base_www_url = "http://" + request.META['HTTP_HOST']
                if base_www_url.find("topcons.net") != -1: #run the daemon only at the frontend
                    cmd = "nohup python %s &"%(qd_fe_scriptfile)
                    os.system(cmd)
#                 try:
#                     subprocess.check_output(cmd)
#                 except subprocess.CalledProcessError, e:
#                     datetime = time.strftime("%Y-%m-%d %H:%M:%S")
#                     myfunc.WriteFile("[%s] %s\n"%(datetime, str(e)), gen_errfile, "a")


                if query['nummodel'] < 0: #go to result page anyway
                    query['jobcounter'] = GetJobCounter(client_ip, isSuperUser,
                            divided_logfile_query, divided_logfile_finished_jobid)
                    return render(request, 'pred/thanks.html', query)
                else:
                    return get_results(request, jobid)

            else:
                query['jobcounter'] = GetJobCounter(client_ip, isSuperUser,
                        divided_logfile_query, divided_logfile_finished_jobid)
                return render(request, 'pred/badquery.html', query)

    # if a GET (or any other method) we'll create a blank form
    else:
        form = SubmissionForm()

    if username in settings.SUPER_USER_LIST:
        isSuperUser = True
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "submitted_seq.log")
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "finished_job.log")
    else:
        isSuperUser = False
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_submitted_seq.log"%(client_ip))
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_finished_job.log"%(client_ip))

    jobcounter = GetJobCounter(client_ip, isSuperUser, divided_logfile_query,
            divided_logfile_finished_jobid)
    info['form'] = form
    info['jobcounter'] = jobcounter
    info['MAX_ALLOWD_NUMMODEL'] = MAX_ALLOWD_NUMMODEL
    return render(request, 'pred/submit_seq.html', info)
#}}}
def get_job_status(jobid):#{{{
    status = "";
    rstdir = "%s/%s"%(path_result, jobid)
    starttagfile = "%s/%s"%(rstdir, "runjob.start")
    finishtagfile = "%s/%s"%(rstdir, "runjob.finish")
    failedtagfile = "%s/%s"%(rstdir, "runjob.failed")
    if os.path.exists(failedtagfile):
        status = "Failed"
    elif os.path.exists(finishtagfile):
        status = "Finished"
    elif os.path.exists(starttagfile):
        status = "Running"
    elif os.path.exists(rstdir):
        status = "Wait"
    return status
#}}}

def login(request):#{{{
    #logout(request)
    info = {}

    username = request.user.username
    client_ip = request.META['REMOTE_ADDR']
    if username in settings.SUPER_USER_LIST:
        isSuperUser = True
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "submitted_seq.log")
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "finished_job.log")
    else:
        isSuperUser = False
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_submitted_seq.log"%(client_ip))
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_finished_job.log"%(client_ip))

    info['username'] = username
    info['isSuperUser'] = isSuperUser
    info['client_ip'] = client_ip

    info['jobcounter'] = GetJobCounter(client_ip, isSuperUser, divided_logfile_query, divided_logfile_finished_jobid)
    return render(request, 'pred/login.html', info)
#}}}
def GetJobCounter(client_ip, isSuperUser, logfile_query, #{{{
        logfile_finished_jobid):
# get job counter for the client_ip
# get the table from runlog, 
# for queued or running jobs, if source=web and numseq=1, check again the tag file in
# each individual folder, since they are queued locally
    jobcounter = {}

    jobcounter['queued'] = 0
    jobcounter['running'] = 0
    jobcounter['finished'] = 0
    jobcounter['failed'] = 0
    jobcounter['nojobfolder'] = 0 #of which the folder jobid does not exist

    jobcounter['queued_idlist'] = []
    jobcounter['running_idlist'] = []
    jobcounter['finished_idlist'] = []
    jobcounter['failed_idlist'] = []
    jobcounter['nojobfolder_idlist'] = []


    if isSuperUser:
        maxdaystoshow = BIG_NUMBER
    else:
        maxdaystoshow = MAX_DAYS_TO_SHOW


    hdl = myfunc.ReadLineByBlock(logfile_query)
    if hdl.failure:
        return jobcounter
    else:
        finished_job_dict = ReadFinishedJobLog(logfile_finished_jobid)
        finished_jobid_set = set([])
        failed_jobid_set = set([])
        for jobid in finished_job_dict:
            status = finished_job_dict[jobid][0]
            rstdir = "%s/%s"%(path_result, jobid)
            if status == "Finished":
                finished_jobid_set.add(jobid)
            elif status == "Failed":
                failed_jobid_set.add(jobid)
        lines = hdl.readlines()
        current_time = datetime.now()
        while lines != None:
            for line in lines:
                strs = line.split("\t")
                if len(strs) < 7:
                    continue
                ip = strs[2]
                if not isSuperUser and ip != client_ip:
                    continue

                submit_date_str = strs[0]
                isValidSubmitDate = True
                try:
                    submit_date = datetime.strptime(submit_date_str, 
                            "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    isValidSubmitDate = False

                if not isValidSubmitDate:
                    continue

                diff_date = current_time - submit_date
                if diff_date.days > maxdaystoshow:
                    continue
                jobid = strs[1]
                rstdir = "%s/%s"%(path_result, jobid)

                if jobid in finished_jobid_set:
                    jobcounter['finished'] += 1
                    jobcounter['finished_idlist'].append(jobid)
                elif jobid in failed_jobid_set:
                    jobcounter['failed'] += 1
                    jobcounter['failed_idlist'].append(jobid)
                else:
                    finishtagfile = "%s/%s"%(rstdir, "runjob.finish")
                    failtagfile = "%s/%s"%(rstdir, "runjob.failed")
                    starttagfile = "%s/%s"%(rstdir, "runjob.start")
                    if not os.path.exists(rstdir):
                        jobcounter['nojobfolder'] += 1
                        jobcounter['nojobfolder_idlist'].append(jobid)
                    elif os.path.exists(failtagfile):
                        jobcounter['failed'] += 1
                        jobcounter['failed_idlist'].append(jobid)
                    elif os.path.exists(finishtagfile):
                        jobcounter['finished'] += 1
                        jobcounter['finished_idlist'].append(jobid)
                    elif os.path.exists(starttagfile):
                        jobcounter['running'] += 1
                        jobcounter['running_idlist'].append(jobid)
                    else:
                        jobcounter['queued'] += 1
                        jobcounter['queued_idlist'].append(jobid)
            lines = hdl.readlines()
        hdl.close()
    return jobcounter
#}}}
def GetNumSameUserInQueue(rstdir, host_ip, email):#{{{
    nummodel_this_user = 1
    logfile = "%s/runjob.log"%(rstdir)
    cmd = [suq_exec, "-b", suq_basedir, "ls"]
    cmdline = " ".join(cmd)
    myfunc.WriteFile("cmdline: " + cmdline +"\n", logfile, "a")
    try:
        suq_ls_content =  myfunc.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError, e:
        myfunc.WriteFile(str(e) +"\n", logfile, "a")
        return nummodel_this_user

    if email != "" or host_ip != "":
        lines = suq_ls_content.split("\n")
        for line in lines:
            if ((email != "" and line.find(email) != -1) or
                (host_ip != "" and line.find(host_ip) != -1)):
                nummodel_this_user += 1

    return nummodel_this_user
#}}}

def ValidateQuery(request, query):#{{{
    query['errinfo_br'] = ""
    query['errinfo_content'] = ""
    query['warninfo'] = ""
    query['filtered_seq'] = ""

    has_pasted_seq = False
    has_upload_seqfile = False
    if query['rawseq'].strip() != "":
        has_pasted_seq = True
    if query['seqfile'] != "":
        has_upload_seqfile = True

    has_pasted_model = False
    has_upload_modelfile = False
    if query['rawmodel'].strip() != "":
        has_pasted_model = True
    if query['modelfile'] != "":
        has_upload_modelfile = True


    if has_pasted_model and has_upload_modelfile:
        query['errinfo_br'] += "Confused input!"
        query['errinfo_content'] = "You should input your model by either "\
                "paste the model in the text area or upload a file, but not both."
        return False
    elif not has_pasted_model and not has_upload_modelfile:
        query['errinfo_br'] += "No input!"
        query['errinfo_content'] = "You should input your query by either "\
                "paste the model in the text area or upload a file. "
        return False
    elif query['modelfile'] != "":
        try:
            fp = request.FILES['modelfile']
            fp.seek(0,2)
            filesize = fp.tell()
            if filesize > MAXSIZE_UPLOAD_MODELFILE_IN_BYTE:
                query['errinfo_br'] += "Size of the uploaded model file exceeds the limit!"
                query['errinfo_content'] += "The file you uploaded exceeds "\
                        "the upper limit %g Mb. Please split your file and "\
                        "upload again."%(MAXSIZE_UPLOAD_MODELFILE_IN_MB)
                return False

            fp.seek(0,0)
            content = fp.read()
        except KeyError:
            query['errinfo_br'] += ""
            query['errinfo_content'] += """
            Failed to read the uploaded file \"%s\"
            """%(query['modelfile'])
            return False
        query['rawmodel'] = content.replace('\r','')

    if has_pasted_seq and has_upload_seqfile:
        query['errinfo_br'] += "Confused input!"
        query['errinfo_content'] = "You should input your sequence by either "\
                "paste the sequence in the text area or upload a file, but not both."
        return False
    elif query['seqfile'] != "":
        try:
            fp = request.FILES['seqfile']
            fp.seek(0,2)
            filesize = fp.tell()
            if filesize > MAXSIZE_UPLOAD_SEQFILE_IN_BYTE:
                query['errinfo_br'] += "Size of the uploaded sequence file exceeds the limit!"
                query['errinfo_content'] += "The file you uploaded exceeds "\
                        "the upper limit %g Mb. Please split your file and "\
                        "upload again."%(MAXSIZE_UPLOAD_SEQFILE_IN_MB)
                return False

            fp.seek(0,0)
            content = fp.read()
        except KeyError:
            query['errinfo_br'] += ""
            query['errinfo_content'] += """
            Failed to read the uploaded file \"%s\"
            """%(query['seqfile'])
            return False
        query['rawseq'] = content

    # parsing the raw model file by the MODEL, ENDMDL tag
    modelList = myfunc.ReadPDBModelFromBuff(query['rawmodel'])

    nummodel = len(modelList)
    query['nummodel'] = nummodel
    query['modelList'] = modelList
    query['filtered_model' ] = ""

    if nummodel < 1:
        query['errinfo_br'] += "The number of models you input is 0!"
        query['errinfo_content'] += "Please check the format of the model you have input.";
        return False
    else:
        tmpli = []
        for ii in xrange(nummodel):
            tmpli.append("MODEL %d"%(ii+1))
            tmpli.append(modelList[ii])
            tmpli.append("ENDMDL")
        query['filtered_model'] = "\n".join(tmpli)

    if query['rawseq'].strip() == "":
        query['filtered_seq'] = ""
    else:
        seqRecordList = []
        myfunc.ReadFastaFromBuffer(query['rawseq'], seqRecordList, True, 0, 0)
# filter empty sequences and any sequeces shorter than 1 amino acids
        newSeqRecordList = []
        isHasEmptySeq = False
        isHasShortSeq = False
        for rd in seqRecordList:
            seq = rd[2].strip()
            if len(seq) == 0:
                isHasEmptySeq = 1
            elif len(seq) < 1:
                isHasShortSeq = 1
            else:
                newSeqRecordList.append(rd)
        seqRecordList = newSeqRecordList

        numseq = len(seqRecordList)
        query['numseq'] = numseq

        if numseq < 1:
            query['errinfo_br'] += "You have input sequence of you model, but the number of input sequences is 0!"

            t_rawseq = query['rawseq'].lstrip()
            if t_rawseq and t_rawseq[0] != '>':
                query['errinfo_content'] += "Bad input format. The FASTA format should have an annotation line start wit '>'. "
            if isHasEmptySeq:
                query['errinfo_content'] += "Empty sequence(s) found. "
            if isHasShortSeq:
                query['errinfo_content'] += "Short sequence(s) < 10 aa found. "
            if not isHasShortSeq and not isHasEmptySeq:
                query['errinfo_content'] += "Please input your sequence in FASTA format"
            return False
        elif numseq > 1:
            query['errinfo_br'] += "You have input sequence of you model, but there are more than one sequences in you input. You are just allowed to input one sequence!"
            return False
        else:
            li_warn_info = []
            li_newseq = []
            for i in xrange(numseq):
                seq = seqRecordList[i][2].strip()
                anno = seqRecordList[i][1].strip()
                seqid = seqRecordList[i][0].strip()
                seq = seq.upper()
                seq = re.sub("[\s\n\r\t]", '', seq)
                li1 = [m.start() for m in re.finditer("[BUZ*]", seq)]
                if len(li1) > 0:
                    for j in xrange(len(li1)):
                        msg = "Amino acid in sequence %s (SeqNo. %d) at position %d "\
                                "(letter: '%s') has been replaced by 'X'"%(seqid,
                                        i+1, li1[j]+1, seq[li1[j]])
                        li_warn_info.append(msg)
                    seq = re.sub("[BUZ*]", "X", seq)
                li_newseq.append(">%s\n%s"%(anno, seq))

            query['filtered_seq'] = "\n".join(li_newseq) # seq content after validation
            query['warninfo'] = "\n".join(li_warn_info)
    return True
#}}}
def ValidateSeq(rawseq):#{{{
# seq is the chunk of fasta file
# return (filtered_seq, seqinfo)
    filtered_seq = ""
    seqinfo = {}
    seqRecordList = []
    myfunc.ReadFastaFromBuffer(rawseq, seqRecordList, True, 0, 0)
    seqinfo['errinfo'] = ""
    seqinfo['warninfo'] = ""

# filter empty sequences and any sequeces shorter than 10 amino acids
    newSeqRecordList = []

    isHasEmptySeq = False
    isHasShortSeq = False
    for rd in seqRecordList:
        seq = rd[2].strip()
        if len(seq) == 0:
            isHasEmptySeq = 1
        elif len(seq) < 10:
            isHasShortSeq = 1
        else:
            newSeqRecordList.append(rd)
    seqRecordList = newSeqRecordList


    numseq = len(seqRecordList)
    seqinfo['numseq'] = numseq
    seqinfo['isValidSeq'] = True
    errinfoList = []

    if numseq < 1:
        errinfoList.append("Number of input sequences is 0!")
        t_rawseq = rawseq.lstrip()
        if t_rawseq and t_rawseq[0] != '>':
            errinfoList.append("Bad input format. The FASTA format should have an annotation line start wit '>'")
        if isHasEmptySeq:
            errinfoList.append("Empty sequence(s) found.")
        if isHasShortSeq:
            errinfoList.append("Short sequence(s) < 10 aa found.")
        if not isHasShortSeq and not isHasEmptySeq:
            errinfoList.append("Please input your sequence in FASTA format.")

        seqinfo['isValidSeq'] = False
    else:
        li_badseq_info = []
        for i in xrange(numseq):
            seq = seqRecordList[i][2].strip()
            anno = seqRecordList[i][1].strip()
            seqid = seqRecordList[i][0].strip()
            seq = seq.upper()
            seq = re.sub("[\s\n\r\t]", '', seq)
            li1 = [m.start() for m in re.finditer("[^ABCDEFGHIKLMNPQRSTUVWYZX*]", seq)]
            if len(li1) > 0:
                for j in xrange(len(li1)):
                    msg = "Bad letter for amino acid in sequence %s (SeqNo. %d) "\
                            "at position %d (letter: '%s')"%(seqid, i+1,
                                    li1[j]+1, seq[li1[j]])
                    li_badseq_info.append(msg)

        if len(li_badseq_info) > 0:
            errinfoList.append("There are bad letters for amino acids in your query!")
            errinfiList += li_badseq_info
            seqinfo['isValidSeq'] = False

        li_warn_info = []
        li_newseq = []
        for i in xrange(numseq):
            seq = seqRecordList[i][2].strip()
            anno = seqRecordList[i][1].strip()
            seqid = seqRecordList[i][0].strip()
            seq = seq.upper()
            seq = re.sub("[\s\n\r\t]", '', seq)
            li1 = [m.start() for m in re.finditer("[BUZ*]", seq)]
            if len(li1) > 0:
                for j in xrange(len(li1)):
                    msg = "Amino acid in sequence %s (SeqNo. %d) at position %d "\
                            "(letter: '%s') has been replaced by 'X'"%(seqid,
                                    i+1, li1[j]+1, seq[li1[j]])
                    li_warn_info.append(msg)
                seq = re.sub("[BUZ*]", "X", seq)
            li_newseq.append(">%s\n%s"%(anno, seq))

        filtered_seq = "\n".join(li_newseq) # seq content after validation
        seqinfo['isValidSeq'] = True
        seqinfo['warinfo'] = "\n".join(li_warn_info)

    seqinfo['errinfo'] = "\n".join(errinfoList)
    return (filtered_seq, seqinfo)
#}}}
def RunQuery(request, query):#{{{
    errmsg = []
    tmpdir = tempfile.mkdtemp(prefix="%s/static/tmp/tmp_"%(SITE_ROOT))
    rstdir = tempfile.mkdtemp(prefix="%s/static/result/rst_"%(SITE_ROOT))
    os.chmod(tmpdir, 0755)
    os.chmod(rstdir, 0755)
    jobid = os.path.basename(rstdir)
    query['jobid'] = jobid

# write files for the query
    jobinfofile = "%s/jobinfo"%(rstdir)
    rawseqfile = "%s/query.raw.fa"%(rstdir)
    seqfile_t = "%s/query.fa"%(tmpdir)
    seqfile_r = "%s/query.fa"%(rstdir)
    modelfile_t = "%s/query.pdb"%(tmpdir)
    modelfile_r = "%s/query.pdb"%(rstdir)
    rawmodelfile = "%s/query.raw.pdb"%(rstdir)
    warnfile = "%s/warn.txt"%(tmpdir)
    logfile = "%s/runjob.log"%(rstdir)

    myfunc.WriteFile("tmpdir = %s\n"%(tmpdir), logfile, "a")

    jobinfo_str = "%s\t%s\t%s\t%s\t%d\t%s\t%s\t%s\n"%(query['date'], jobid,
            query['client_ip'], query['nummodel'],
            len(query['rawseq']),query['jobname'], query['email'],
            query['method_submission'])
    errmsg.append(myfunc.WriteFile(jobinfo_str, jobinfofile, "w"))
    if query['rawseq'].strip() != "":
        errmsg.append(myfunc.WriteFile(query['rawseq'], rawseqfile, "w"))
    errmsg.append(myfunc.WriteFile(query['rawmodel'], rawmodelfile, "w"))
    if  query['filtered_seq'] != "":
        errmsg.append(myfunc.WriteFile(query['filtered_seq'], seqfile_t, "w"))
        errmsg.append(myfunc.WriteFile(query['filtered_seq'], seqfile_r, "w"))
    errmsg.append(myfunc.WriteFile(query['filtered_model'], modelfile_t, "w"))
    errmsg.append(myfunc.WriteFile(query['filtered_model'], modelfile_r, "w"))
    base_www_url = "http://" + request.META['HTTP_HOST']
    query['base_www_url'] = base_www_url

    if query['nummodel'] <= MAX_ALLOWD_NUMMODEL: # batch submission, max 5 seq
        query['nummodel_this_user'] = query['nummodel']
        SubmitQueryToLocalQueue(query, tmpdir, rstdir)

    forceruntagfile = "%s/forcerun"%(rstdir)
    if query['isForceRun']:
        myfunc.WriteFile("", forceruntagfile)
    return jobid
#}}}
def RunQuery_wsdl(rawseq, filtered_seq, seqinfo):#{{{
    errmsg = []
    tmpdir = tempfile.mkdtemp(prefix="%s/static/tmp/tmp_"%(SITE_ROOT))
    rstdir = tempfile.mkdtemp(prefix="%s/static/result/rst_"%(SITE_ROOT))
    os.chmod(tmpdir, 0755)
    os.chmod(rstdir, 0755)
    jobid = os.path.basename(rstdir)
    seqinfo['jobid'] = jobid
    numseq = seqinfo['numseq']

# write files for the query
    jobinfofile = "%s/jobinfo"%(rstdir)
    rawseqfile = "%s/query.raw.fa"%(rstdir)
    seqfile_t = "%s/query.fa"%(tmpdir)
    seqfile_r = "%s/query.fa"%(rstdir)
    warnfile = "%s/warn.txt"%(tmpdir)
    jobinfo_str = "%s\t%s\t%s\t%s\t%d\t%s\t%s\t%s\n"%(seqinfo['date'], jobid,
            seqinfo['client_ip'], seqinfo['numseq'],
            len(rawseq),seqinfo['jobname'], seqinfo['email'],
            seqinfo['method_submission'])
    errmsg.append(myfunc.WriteFile(jobinfo_str, jobinfofile, "w"))
    errmsg.append(myfunc.WriteFile(rawseq, rawseqfile, "w"))
    errmsg.append(myfunc.WriteFile(filtered_seq, seqfile_t, "w"))
    errmsg.append(myfunc.WriteFile(filtered_seq, seqfile_r, "w"))
    base_www_url = "http://" + seqinfo['hostname']
    seqinfo['base_www_url'] = base_www_url

    # changed 2015-03-26, any jobs submitted via wsdl is hadndel
    return jobid
#}}}
def RunQuery_wsdl_local(rawseq, filtered_seq, seqinfo):#{{{
# submit the wsdl job to the local queue
    errmsg = []
    tmpdir = tempfile.mkdtemp(prefix="%s/static/tmp/tmp_"%(SITE_ROOT))
    rstdir = tempfile.mkdtemp(prefix="%s/static/result/rst_"%(SITE_ROOT))
    os.chmod(tmpdir, 0755)
    os.chmod(rstdir, 0755)
    jobid = os.path.basename(rstdir)
    seqinfo['jobid'] = jobid
    numseq = seqinfo['numseq']

# write files for the query
    jobinfofile = "%s/jobinfo"%(rstdir)
    rawseqfile = "%s/query.raw.fa"%(rstdir)
    seqfile_t = "%s/query.fa"%(tmpdir)
    seqfile_r = "%s/query.fa"%(rstdir)
    warnfile = "%s/warn.txt"%(tmpdir)
    jobinfo_str = "%s\t%s\t%s\t%s\t%d\t%s\t%s\t%s\n"%(seqinfo['date'], jobid,
            seqinfo['client_ip'], seqinfo['numseq'],
            len(rawseq),seqinfo['jobname'], seqinfo['email'],
            seqinfo['method_submission'])
    errmsg.append(myfunc.WriteFile(jobinfo_str, jobinfofile, "w"))
    errmsg.append(myfunc.WriteFile(rawseq, rawseqfile, "w"))
    errmsg.append(myfunc.WriteFile(filtered_seq, seqfile_t, "w"))
    errmsg.append(myfunc.WriteFile(filtered_seq, seqfile_r, "w"))
    base_www_url = "http://" + seqinfo['hostname']
    seqinfo['base_www_url'] = base_www_url

    rtvalue = SubmitQueryToLocalQueue(seqinfo, tmpdir, rstdir)
    if rtvalue != 0:
        return ""
    else:
        return jobid
#}}}
def SubmitQueryToLocalQueue(query, tmpdir, rstdir):#{{{
    scriptfile = "%s/app/submit_job_to_queue.py"%(SITE_ROOT)
    rstdir = "%s/%s"%(path_result, query['jobid'])
    errfile = "%s/runjob.err"%(rstdir)
    debugfile = "%s/debug.log"%(rstdir) #this log only for debugging
    logfile = "%s/runjob.log"%(rstdir)
    rmsg = ""

    cmd = [python_exec, scriptfile, "-nmodel", "%d"%query['nummodel'], "-nmodel-this-user",
            "%d"%query['nummodel_this_user'], "-jobid", query['jobid'],
            "-outpath", rstdir, "-datapath", tmpdir, "-baseurl",
            query['base_www_url'] ]
    if query['email'] != "":
        cmd += ["-email", query['email']]
    if query['client_ip'] != "":
        cmd += ["-host", query['client_ip']]
    if query['isForceRun']:
        cmd += ["-force"]
    if query['isKeepFiles']:
        cmd += ["-k", "yes"]
    if query['targetlength'] != None:
        cmd += ['-t', str(query['targetlength'])]
    cmdline = " ".join(cmd)
    try:
        rmsg = myfunc.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError, e:
        failtagfile = "%s/%s"%(rstdir, "runjob.failed")
        if not os.path.exists(failtagfile):
            date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            myfunc.WriteFile(date, failtagfile)
        myfunc.WriteFile(str(e)+"\n", errfile, "a")
        myfunc.WriteFile("cmdline: " + cmdline +"\n", debugfile, "a")
        myfunc.WriteFile(rmsg+"\n", errfile, "a")

        return 1

    return 0

#}}}

def thanks(request):#{{{
    #print "request.POST at thanks:", request.POST
    return HttpResponse("Thanks")
#}}}

def get_queue(request):#{{{
    errfile = "%s/server.err"%(path_result)
    info = {}
    username = request.user.username
    client_ip = request.META['REMOTE_ADDR']
    if username in settings.SUPER_USER_LIST:
        isSuperUser = True
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "submitted_seq.log")
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "finished_job.log")
    else:
        isSuperUser = False
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_submitted_seq.log"%(client_ip))
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_finished_job.log"%(client_ip))

    info['username'] = username
    info['isSuperUser'] = isSuperUser
    info['client_ip'] = client_ip

    status = "Queued"
    if isSuperUser:
        info['header'] = ["No.", "JobID","JobName", "NumModel",
                "Email", "Host", "QueueTime","RunTime", "Date", "Source"]
    else:
        info['header'] = ["No.", "JobID","JobName", "NumModel",
                "Email", "QueueTime","RunTime", "Date", "Source"]

    hdl = myfunc.ReadLineByBlock(divided_logfile_query)
    if hdl.failure:
        info['errmsg'] = ""
        pass
    else:
        finished_jobid_list = []
        if os.path.exists(divided_logfile_finished_jobid):
            finished_jobid_list = myfunc.ReadIDList2(divided_logfile_finished_jobid, 0, None)
        finished_jobid_set = set(finished_jobid_list)
        jobRecordList = []
        lines = hdl.readlines()
        current_time = datetime.now()
        while lines != None:
            for line in lines:
                strs = line.split("\t")
                if len(strs) < 7:
                    continue
                ip = strs[2]
                if not isSuperUser and ip != client_ip:
                    continue
                jobid = strs[1]
                if jobid in finished_jobid_set:
                    continue

                rstdir = "%s/%s"%(path_result, jobid)
                starttagfile = "%s/%s"%(rstdir, "runjob.start")
                failedtagfile = "%s/%s"%(rstdir, "runjob.failed")
                finishtagfile = "%s/%s"%(rstdir, "runjob.finish")
                if (os.path.exists(rstdir) and 
                        not os.path.exists(starttagfile) and
                        not os.path.exists(failedtagfile) and
                        not os.path.exists(finishtagfile)):
                    jobRecordList.append(jobid)
            lines = hdl.readlines()
        hdl.close()

        jobid_inqueue_list = []
        rank = 0
        for jobid in jobRecordList:
            rank += 1
            ip =  ""
            jobname = ""
            email = ""
            method_submission = "web"
            nummodel = 1
            rstdir = "%s/%s"%(path_result, jobid)

            submit_date_str = ""
            finish_date_str = ""
            start_date_str = ""

            jobinfofile = "%s/jobinfo"%(rstdir)
            jobinfo = myfunc.ReadFile(jobinfofile).strip()
            jobinfolist = jobinfo.split("\t")
            if len(jobinfolist) >= 8:
                submit_date_str = jobinfolist[0]
                ip = jobinfolist[2]
                nummodel = int(jobinfolist[3])
                jobname = jobinfolist[5]
                email = jobinfolist[6]
                method_submission = jobinfolist[7]

            starttagfile = "%s/runjob.start"%(rstdir)
            queuetime = ""
            runtime = ""
            isValidSubmitDate = True
            try:
                submit_date = datetime.strptime(submit_date_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                isValidSubmitDate = False

            if isValidSubmitDate:
                queuetime = myfunc.date_diff(submit_date, current_time)

            if isSuperUser:
                jobid_inqueue_list.append([rank, jobid, jobname[:20],
                    nummodel, email, ip, queuetime, runtime,
                    submit_date_str, method_submission])
            else:
                jobid_inqueue_list.append([rank, jobid, jobname[:20],
                    nummodel, email, queuetime, runtime,
                    submit_date_str, method_submission])


        info['BASEURL'] = BASEURL
        info['content'] = jobid_inqueue_list
        info['numjob'] = len(jobid_inqueue_list)
        info['DATATABLE_THRESHOLD'] = 20

    info['jobcounter'] = GetJobCounter(client_ip, isSuperUser,
            divided_logfile_query, divided_logfile_finished_jobid)
    return render(request, 'pred/queue.html', info)
#}}}
def get_running(request):#{{{
    # Get running jobs
    errfile = "%s/server.err"%(path_result)

    status = "Running"

    info = {}

    client_ip = request.META['REMOTE_ADDR']
    username = request.user.username
    if username in settings.SUPER_USER_LIST:
        isSuperUser = True
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "submitted_seq.log")
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "finished_job.log")
    else:
        isSuperUser = False
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_submitted_seq.log"%(client_ip))
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_finished_job.log"%(client_ip))

    info['username'] = username
    info['isSuperUser'] = isSuperUser
    info['client_ip'] = client_ip

    hdl = myfunc.ReadLineByBlock(divided_logfile_query)
    if hdl.failure:
        info['errmsg'] = ""
        pass
    else:
        finished_jobid_list = []
        if os.path.exists(divided_logfile_finished_jobid):
            finished_jobid_list = myfunc.ReadIDList2(divided_logfile_finished_jobid, 0, None)
        finished_jobid_set = set(finished_jobid_list)
        jobRecordList = []
        lines = hdl.readlines()
        current_time = datetime.now()
        while lines != None:
            for line in lines:
                strs = line.split("\t")
                if len(strs) < 7:
                    continue
                ip = strs[2]
                if not isSuperUser and ip != client_ip:
                    continue
                jobid = strs[1]
                if jobid in finished_jobid_set:
                    continue
                rstdir = "%s/%s"%(path_result, jobid)
                starttagfile = "%s/%s"%(rstdir, "runjob.start")
                finishtagfile = "%s/%s"%(rstdir, "runjob.finish")
                failedtagfile = "%s/%s"%(rstdir, "runjob.failed")
                if (os.path.exists(starttagfile) and (not
                    os.path.exists(finishtagfile) and not
                    os.path.exists(failedtagfile))):
                    jobRecordList.append(jobid)
            lines = hdl.readlines()
        hdl.close()

        jobid_inqueue_list = []
        rank = 0
        for jobid in jobRecordList:
            rank += 1
            ip =  ""
            jobname = ""
            email = ""
            method_submission = "web"
            nummodel = 1
            rstdir = "%s/%s"%(path_result, jobid)

            submit_date_str = ""
            finish_date_str = ""
            start_date_str = ""


            jobinfofile = "%s/jobinfo"%(rstdir)
            jobinfo = myfunc.ReadFile(jobinfofile).strip()
            jobinfolist = jobinfo.split("\t")
            if len(jobinfolist) >= 8:
                submit_date_str = jobinfolist[0]
                ip = jobinfolist[2]
                nummodel = int(jobinfolist[3])
                jobname = jobinfolist[5]
                email = jobinfolist[6]
                method_submission = jobinfolist[7]

            starttagfile = "%s/runjob.start"%(rstdir)
            queuetime = ""
            runtime = ""
            isValidSubmitDate = True
            isValidStartDate = True
            try:
                submit_date = datetime.strptime(submit_date_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                isValidSubmitDate = False
            start_date_str = myfunc.ReadFile(starttagfile).strip()
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                isValidStartDate = False
            if isValidStartDate:
                runtime = myfunc.date_diff(start_date, current_time)
            if isValidStartDate and isValidSubmitDate:
                queuetime = myfunc.date_diff(submit_date, start_date)

            if isSuperUser:
                jobid_inqueue_list.append([rank, jobid, jobname[:20],
                    nummodel, email, ip, queuetime, runtime,
                    submit_date_str, method_submission])
            else:
                jobid_inqueue_list.append([rank, jobid, jobname[:20],
                    nummodel, email, queuetime, runtime,
                    submit_date_str, method_submission])


        info['BASEURL'] = BASEURL
        if info['isSuperUser']:
            info['header'] = ["No.", "JobID","JobName", "NumModel",
                    "Email", "Host", "QueueTime","RunTime", "Date", "Source"]
        else:
            info['header'] = ["No.", "JobID","JobName", "NumModel",
                    "Email", "QueueTime","RunTime", "Date", "Source"]
        info['content'] = jobid_inqueue_list
        info['numjob'] = len(jobid_inqueue_list)
        info['DATATABLE_THRESHOLD'] = 20

    info['jobcounter'] = GetJobCounter(client_ip, isSuperUser, divided_logfile_query, divided_logfile_finished_jobid)
    return render(request, 'pred/running.html', info)
#}}}
def get_finished_job(request):#{{{
    info = {}
    info['BASEURL'] = BASEURL


    username = request.user.username
    client_ip = request.META['REMOTE_ADDR']
    if username in settings.SUPER_USER_LIST:
        isSuperUser = True
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "submitted_seq.log")
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "finished_job.log")
    else:
        isSuperUser = False
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_submitted_seq.log"%(client_ip))
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_finished_job.log"%(client_ip))

    info['username'] = username
    info['isSuperUser'] = isSuperUser
    info['client_ip'] = client_ip

    if isSuperUser:
        maxdaystoshow = BIG_NUMBER
        info['header'] = ["No.", "JobID","JobName", "NumModel",
                "Email", "Host", "QueueTime","RunTime", "Date", "Source"]
    else:
        maxdaystoshow = MAX_DAYS_TO_SHOW
        info['header'] = ["No.", "JobID","JobName", "NumModel",
                "Email", "QueueTime","RunTime", "Date", "Source"]

    info['MAX_DAYS_TO_SHOW'] = maxdaystoshow

    hdl = myfunc.ReadLineByBlock(divided_logfile_query)
    if hdl.failure:
        #info['errmsg'] = "Failed to retrieve finished job information!"
        info['errmsg'] = ""
        pass
    else:
        finished_job_dict = ReadFinishedJobLog(divided_logfile_finished_jobid)
        jobRecordList = []
        lines = hdl.readlines()
        current_time = datetime.now()
        while lines != None:
            for line in lines:
                strs = line.split("\t")
                if len(strs) < 7:
                    continue
                ip = strs[2]
                if not isSuperUser and ip != client_ip:
                    continue

                submit_date_str = strs[0]
                isValidSubmitDate = True
                try:
                    submit_date = datetime.strptime(submit_date_str,
                            "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    isValidSubmitDate = False
                if not isValidSubmitDate:
                    continue

                diff_date = current_time - submit_date
                if diff_date.days > maxdaystoshow:
                    continue
                jobid = strs[1]
                rstdir = "%s/%s"%(path_result, jobid)
                if jobid in finished_job_dict:
                    status = finished_job_dict[jobid][0]
                    if status == "Finished":
                        jobRecordList.append(jobid)
                else:
                    finishtagfile = "%s/%s"%(rstdir, "runjob.finish")
                    failedtagfile = "%s/%s"%(rstdir, "runjob.failed")
                    if (os.path.exists(finishtagfile) and
                            not os.path.exists(failedtagfile)):
                        jobRecordList.append(jobid)
            lines = hdl.readlines()
        hdl.close()

        finished_job_info_list = []
        rank = 0
        for jobid in jobRecordList:
            rank += 1
            ip =  ""
            jobname = ""
            email = ""
            method_submission = "web"
            nummodel = 1
            rstdir = "%s/%s"%(path_result, jobid)
            starttagfile = "%s/runjob.start"%(rstdir)
            finishtagfile = "%s/runjob.finish"%(rstdir)

            submit_date_str = ""
            finish_date_str = ""
            start_date_str = ""

            if jobid in finished_job_dict:
                status = finished_job_dict[jobid][0]
                jobname = finished_job_dict[jobid][1]
                ip = finished_job_dict[jobid][2]
                email = finished_job_dict[jobid][3]
                nummodel = finished_job_dict[jobid][4]
                method_submission = finished_job_dict[jobid][5]
                submit_date_str = finished_job_dict[jobid][6]
                start_date_str = finished_job_dict[jobid][7]
                finish_date_str = finished_job_dict[jobid][8]
            else:
                jobinfofile = "%s/jobinfo"%(rstdir)
                jobinfo = myfunc.ReadFile(jobinfofile).strip()
                jobinfolist = jobinfo.split("\t")
                if len(jobinfolist) >= 8:
                    submit_date_str = jobinfolist[0]
                    nummodel = int(jobinfolist[3])
                    jobname = jobinfolist[5]
                    email = jobinfolist[6]
                    method_submission = jobinfolist[7]

            isValidSubmitDate = True
            isValidStartDate = True
            isValidFinishDate = True
            try:
                submit_date = datetime.strptime(submit_date_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                isValidSubmitDate = False
            start_date_str = myfunc.ReadFile(starttagfile).strip()
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                isValidStartDate = False
            finish_date_str = myfunc.ReadFile(finishtagfile).strip()
            try:
                finish_date = datetime.strptime(finish_date_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                isValidFinishDate = False

            queuetime = ""
            runtime = ""

            if isValidStartDate and isValidFinishDate:
                runtime = myfunc.date_diff(start_date, finish_date)
            if isValidSubmitDate and isValidStartDate:
                queuetime = myfunc.date_diff(submit_date, start_date)

            if info['isSuperUser']:
                finished_job_info_list.append([rank, jobid, jobname[:20],
                    str(nummodel), email, ip, queuetime, runtime, submit_date_str,
                    method_submission])
            else:
                finished_job_info_list.append([rank, jobid, jobname[:20],
                    str(nummodel), email, queuetime, runtime, submit_date_str,
                    method_submission])

        info['content'] = finished_job_info_list
        info['numjob'] = len(finished_job_info_list)
        info['DATATABLE_THRESHOLD'] = 20

    info['jobcounter'] = GetJobCounter(client_ip, isSuperUser,
            divided_logfile_query, divided_logfile_finished_jobid)
    return render(request, 'pred/finished_job.html', info)
#}}}
def get_failed_job(request):#{{{
    info = {}

    username = request.user.username
    client_ip = request.META['REMOTE_ADDR']
    if username in settings.SUPER_USER_LIST:
        isSuperUser = True
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "submitted_seq.log")
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "failed_job.log")
    else:
        isSuperUser = False
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_submitted_seq.log"%(client_ip))
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_failed_job.log"%(client_ip))

    info['username'] = username
    info['isSuperUser'] = isSuperUser
    info['client_ip'] = client_ip


    if isSuperUser:
        maxdaystoshow = BIG_NUMBER
        info['header'] = ["No.", "JobID","JobName", "NumModel", "Email",
                "Host", "QueueTime","RunTime", "Date", "Source"]
    else:
        maxdaystoshow = MAX_DAYS_TO_SHOW
        info['header'] = ["No.", "JobID","JobName", "NumModel", "Email",
                "QueueTime","RunTime", "Date", "Source"]


    info['MAX_DAYS_TO_SHOW'] = maxdaystoshow
    info['BASEURL'] = BASEURL

    hdl = myfunc.ReadLineByBlock(divided_logfile_query)
    if hdl.failure:
#         info['errmsg'] = "Failed to retrieve finished job information!"
        info['errmsg'] = ""
        pass
    else:
        finished_job_dict = ReadFinishedJobLog(divided_logfile_finished_jobid)
        jobRecordList = []
        lines = hdl.readlines()
        current_time = datetime.now()
        while lines != None:
            for line in lines:
                strs = line.split("\t")
                if len(strs) < 7:
                    continue
                ip = strs[2]
                if not isSuperUser and ip != client_ip:
                    continue

                submit_date_str = strs[0]
                submit_date = datetime.strptime(submit_date_str, "%Y-%m-%d %H:%M:%S")
                diff_date = current_time - submit_date
                if diff_date.days > maxdaystoshow:
                    continue
                jobid = strs[1]
                rstdir = "%s/%s"%(path_result, jobid)

                if jobid in finished_job_dict:
                    status = finished_job_dict[jobid][0]
                    if status == "Failed":
                        jobRecordList.append(jobid)
                else:
                    failtagfile = "%s/%s"%(rstdir, "runjob.failed")
                    if os.path.exists(rstdir) and os.path.exists(failtagfile):
                        jobRecordList.append(jobid)
            lines = hdl.readlines()
        hdl.close()


        failed_job_info_list = []
        rank = 0
        for jobid in jobRecordList:
            rank += 1

            ip = ""
            jobname = ""
            email = ""
            method_submission = ""
            nummodel = 1
            submit_date_str = ""

            rstdir = "%s/%s"%(path_result, jobid)
            starttagfile = "%s/runjob.start"%(rstdir)
            failtagfile = "%s/runjob.failed"%(rstdir)

            if jobid in finished_job_dict:
                submit_date_str = finished_job_dict[jobid][0]
                jobname = finished_job_dict[jobid][1]
                ip = finished_job_dict[jobid][2]
                email = finished_job_dict[jobid][3]
                nummodel = finished_job_dict[jobid][4]
                method_submission = finished_job_dict[jobid][5]
                submit_date_str = finished_job_dict[jobid][6]
                start_date_str = finished_job_dict[jobid][ 7]
                finish_date_str = finished_job_dict[jobid][8]
            else:
                jobinfofile = "%s/jobinfo"%(rstdir)
                jobinfo = myfunc.ReadFile(jobinfofile).strip()
                jobinfolist = jobinfo.split("\t")
                if len(jobinfolist) >= 8:
                    submit_date_str = jobinfolist[0]
                    nummodel = int(jobinfolist[3])
                    jobname = jobinfolist[5]
                    email = jobinfolist[6]
                    method_submission = jobinfolist[7]


            isValidStartDate = True
            isValidFailedDate = True
            isValidSubmitDate = True

            try:
                submit_date = datetime.strptime(submit_date_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                isValidSubmitDate = False

            start_date_str = myfunc.ReadFile(starttagfile).strip()
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                isValidStartDate = False
            failed_date_str = myfunc.ReadFile(failtagfile).strip()
            try:
                failed_date = datetime.strptime(failed_date_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                isValidFailedDate = False

            queuetime = ""
            runtime = ""

            if isValidStartDate and isValidFailedDate:
                runtime = myfunc.date_diff(start_date, failed_date)
            if isValidSubmitDate and isValidStartDate:
                queuetime = myfunc.date_diff(submit_date, start_date)

            if info['isSuperUser']:
                failed_job_info_list.append([rank, jobid, jobname[:20],
                    str(nummodel), email, ip, queuetime, runtime, submit_date_str,
                    method_submission])
            else:
                failed_job_info_list.append([rank, jobid, jobname[:20],
                    str(nummodel), email, queuetime, runtime, submit_date_str,
                    method_submission])


        info['content'] = failed_job_info_list
        info['numjob'] = len(failed_job_info_list)
        info['DATATABLE_THRESHOLD'] = 20

    info['jobcounter'] = GetJobCounter(client_ip, isSuperUser,
            divided_logfile_query, divided_logfile_finished_jobid)
    return render(request, 'pred/failed_job.html', info)
#}}}

def search(request):#{{{
    if 'q' in request.GET and request.GET['q']:
        q = request.GET['q']
        seq = Query.objects.filter(seqname=q)
        return render(request, 'search_results.html',
            {'seq': seq, 'query': q})
    else:
        return HttpResponse('Please submit a search term.')
#}}}
def get_help(request):#{{{
    info = {}

    username = request.user.username
    client_ip = request.META['REMOTE_ADDR']
    if username in settings.SUPER_USER_LIST:
        isSuperUser = True
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "submitted_seq.log")
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "finished_job.log")
    else:
        isSuperUser = False
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_submitted_seq.log"%(client_ip))
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_finished_job.log"%(client_ip))

    info['username'] = username
    info['isSuperUser'] = isSuperUser
    info['client_ip'] = client_ip

    info['jobcounter'] = GetJobCounter(client_ip, isSuperUser,
            divided_logfile_query, divided_logfile_finished_jobid)

    return render(request, 'pred/help.html', info)
#}}}
def get_news(request):#{{{
    info = {}

    username = request.user.username
    client_ip = request.META['REMOTE_ADDR']
    if username in settings.SUPER_USER_LIST:
        isSuperUser = True
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "submitted_seq.log")
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "finished_job.log")
    else:
        isSuperUser = False
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_submitted_seq.log"%(client_ip))
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_finished_job.log"%(client_ip))

    info['username'] = username
    info['isSuperUser'] = isSuperUser
    info['client_ip'] = client_ip

    newsfile = "%s/%s/%s"%(SITE_ROOT, "static/doc", "news.txt")
    newsList = []
    if os.path.exists(newsfile):
        newsList = myfunc.ReadNews(newsfile)
    info['newsList'] = newsList
    info['newsfile'] = newsfile

    info['jobcounter'] = GetJobCounter(client_ip, isSuperUser,
            divided_logfile_query, divided_logfile_finished_jobid)

    return render(request, 'pred/news.html', info)
#}}}
def get_reference(request):#{{{
    info = {}

    username = request.user.username
    client_ip = request.META['REMOTE_ADDR']
    if username in settings.SUPER_USER_LIST:
        isSuperUser = True
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "submitted_seq.log")
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "finished_job.log")
    else:
        isSuperUser = False
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_submitted_seq.log"%(client_ip))
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_finished_job.log"%(client_ip))

    info['username'] = username
    info['isSuperUser'] = isSuperUser
    info['client_ip'] = client_ip

    info['jobcounter'] = GetJobCounter(client_ip, isSuperUser,
            divided_logfile_query, divided_logfile_finished_jobid)

    return render(request, 'pred/reference.html', info)
#}}}


def get_serverstatus(request):#{{{
    info = {}

    username = request.user.username
    client_ip = request.META['REMOTE_ADDR']
    if username in settings.SUPER_USER_LIST:
        isSuperUser = True
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "submitted_seq.log")
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "finished_job.log")
    else:
        isSuperUser = False
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_submitted_seq.log"%(client_ip))
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_finished_job.log"%(client_ip))

    info['username'] = username
    info['isSuperUser'] = isSuperUser
    info['client_ip'] = client_ip
    


    logfile_finished =  "%s/%s/%s"%(SITE_ROOT, "static/log", "finished_job.log")
    logfile_runjob =  "%s/%s/%s"%(SITE_ROOT, "static/log", "runjob_log.log")

    submitjoblogfile = "%s/submitted_seq.log"%(path_log)
    runjoblogfile = "%s/runjob_log.log"%(path_log)
    finishedjoblogfile = "%s/finished_job.log"%(path_log)

# finished sequences submitted by wsdl
# finished sequences submitted by web

# javascript to show finished sequences of the data (histogram)

# get jobs queued locally (at the front end)
    num_seq_in_local_queue = 0
    cmd = [suq_exec, "-b", suq_basedir, "ls"]
    cmdline = " ".join(cmd)
    try:
        suq_ls_content =  myfunc.check_output(cmd, stderr=subprocess.STDOUT)
        lines = suq_ls_content.split("\n")
        cntjob = 0
        for line in lines:
            if line.find("runjob") != -1:
                cntjob += 1
        num_seq_in_local_queue = cntjob
    except subprocess.CalledProcessError, e:
        datetime = time.strftime("%Y-%m-%d %H:%M:%S")
        myfunc.WriteFile("[%s] %s\n"%(datetime, str(e)), gen_errfile, "a")

# get number of finished seqs
    finishedjoblogfile = "%s/finished_job.log"%(path_log)
    finished_job_dict = {}
    if os.path.exists(finishedjoblogfile):
        finished_job_dict = myfunc.ReadFinishedJobLog(finishedjoblogfile)
# editing here 2015-05-13

    total_num_finished_seq = 0
    startdate = ""
    submitdatelist = []
    for jobid in finished_job_dict:
        li = finished_job_dict[jobid]
        try:
            numseq = int(li[4])
        except:
            numseq = 1
        try:
            submitdatelist.append(li[6])
        except:
            pass
        total_num_finished_seq += numseq

    submitdatelist = sorted(submitdatelist, reverse=False)
    if len(submitdatelist)>0:
        startdate = submitdatelist[0].split()[0]


    info['num_seq_in_local_queue'] = num_seq_in_local_queue
    info['total_num_finished_seq'] = total_num_finished_seq
    info['num_finished_seqs_str'] = str(total_num_finished_seq)
    info['startdate'] = startdate
    info['jobcounter'] = GetJobCounter(client_ip, isSuperUser,
            divided_logfile_query, divided_logfile_finished_jobid)

    return render(request, 'pred/serverstatus.html', info)
#}}}
def get_example(request):#{{{
    info = {}

    username = request.user.username
    client_ip = request.META['REMOTE_ADDR']
    if username in settings.SUPER_USER_LIST:
        isSuperUser = True
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "submitted_seq.log")
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "finished_job.log")
    else:
        isSuperUser = False
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_submitted_seq.log"%(client_ip))
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_finished_job.log"%(client_ip))

    info['username'] = username
    info['isSuperUser'] = isSuperUser
    info['client_ip'] = client_ip

    info['jobcounter'] = GetJobCounter(client_ip, isSuperUser,
            divided_logfile_query, divided_logfile_finished_jobid)

    return render(request, 'pred/example.html', info)
#}}}
def proq2(request):#{{{
    url_proq2 = "http://bioinfo.ifm.liu.se/ProQ2/index.php"
    return HttpResponseRedirect(url_proq2);
#}}}
def help_wsdl_api(request):#{{{
    info = {}

    username = request.user.username
    client_ip = request.META['REMOTE_ADDR']
    if username in settings.SUPER_USER_LIST:
        isSuperUser = True
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "submitted_seq.log")
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "finished_job.log")
    else:
        isSuperUser = False
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_submitted_seq.log"%(client_ip))
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_finished_job.log"%(client_ip))

    info['username'] = username
    info['isSuperUser'] = isSuperUser
    info['client_ip'] = client_ip


    api_script_rtname =  "topcons2_wsdl"
    extlist = [".py"]
    api_script_lang_list = ["Python"]
    api_script_info_list = []

    for i in xrange(len(extlist)):
        ext = extlist[i]
        api_script_file = "%s/%s/%s"%(SITE_ROOT,
                "static/download/script", "%s%s"%(api_script_rtname,
                    ext))
        api_script_basename = os.path.basename(api_script_file)
        if not os.path.exists(api_script_file):
            continue
        cmd = [api_script_file, "-h"]
        try:
            usage = myfunc.check_output(cmd)
        except subprocess.CalledProcessError, e:
            usage = ""
        api_script_info_list.append([api_script_lang_list[i], api_script_basename, usage])

    info['api_script_info_list'] = api_script_info_list
    info['jobcounter'] = GetJobCounter(client_ip, isSuperUser,
            divided_logfile_query, divided_logfile_finished_jobid)

    return render(request, 'pred/help_wsdl_api.html', info)
#}}}
def download(request):#{{{
    info = {}

    username = request.user.username
    client_ip = request.META['REMOTE_ADDR']
    if username in settings.SUPER_USER_LIST:
        isSuperUser = True
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "submitted_seq.log")
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "finished_job.log")
    else:
        isSuperUser = False
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_submitted_seq.log"%(client_ip))
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_finished_job.log"%(client_ip))

    info['username'] = username
    info['isSuperUser'] = isSuperUser
    info['client_ip'] = client_ip
    info['zipfile_wholepackage'] = ""
    info['size_wholepackage'] = ""
    size_wholepackage = 0
    zipfile_wholepackage = "%s/%s/%s"%(SITE_ROOT, "static/download", "boctopus2_newset_hhblits.zip")
    if os.path.exists(zipfile_wholepackage):
        info['zipfile_wholepackage'] = os.path.basename(zipfile_wholepackage)
        size_wholepackage = os.path.getsize(os.path.realpath(zipfile_wholepackage))
        size_wholepackage_str = myfunc.Size_byte2human(size_wholepackage)
        info['size_wholepackage'] = size_wholepackage_str

    info['jobcounter'] = GetJobCounter(client_ip, isSuperUser,
            divided_logfile_query, divided_logfile_finished_jobid)

    return render(request, 'pred/download.html', info)
#}}}

def get_results(request, jobid="1"):#{{{
    resultdict = {}

    username = request.user.username
    client_ip = request.META['REMOTE_ADDR']
    if username in settings.SUPER_USER_LIST:
        isSuperUser = True
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "submitted_seq.log")
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "finished_job.log")
    else:
        isSuperUser = False
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_submitted_seq.log"%(client_ip))
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_finished_job.log"%(client_ip))

    resultdict['username'] = username
    resultdict['isSuperUser'] = isSuperUser
    resultdict['client_ip'] = client_ip


    #img1 = "%s/%s/%s/%s"%(SITE_ROOT, "result", jobid, "PconsC2.s400.jpg")
    #url_img1 =  serve(request, os.path.basename(img1), os.path.dirname(img1))
    rstdir = "%s/%s"%(path_result, jobid)
    outpathname = jobid
    resultfile = "%s/%s/%s/%s"%(rstdir, jobid, outpathname, "query.result.txt")
    tarball = "%s/%s.tar.gz"%(rstdir, outpathname)
    zipfile = "%s/%s.zip"%(rstdir, outpathname)
    starttagfile = "%s/%s"%(rstdir, "runjob.start")
    finishtagfile = "%s/%s"%(rstdir, "runjob.finish")
    failtagfile = "%s/%s"%(rstdir, "runjob.failed")
    errfile = "%s/%s"%(rstdir, "runjob.err")
    query_seqfile = "%s/%s"%(rstdir, "query.fa")
    raw_query_seqfile = "%s/%s"%(rstdir, "query.raw.fa")
    raw_query_modelfile = "%s/%s"%(rstdir, "query.raw.pdb")
    seqid_index_mapfile = "%s/%s/%s"%(rstdir,jobid, "seqid_index_map.txt")
    finished_model_file = "%s/%s/finished_models.txt"%(rstdir, jobid)
    statfile = "%s/%s/stat.txt"%(rstdir, jobid)
    method_submission = "web"

    jobinfofile = "%s/jobinfo"%(rstdir)
    jobinfo = myfunc.ReadFile(jobinfofile).strip()
    jobinfolist = jobinfo.split("\t")
    if len(jobinfolist) >= 8:
        submit_date_str = jobinfolist[0]
        nummodel = int(jobinfolist[3])
        jobname = jobinfolist[5]
        email = jobinfolist[6]
        method_submission = jobinfolist[7]
    else:
        submit_date_str = ""
        nummodel = 1
        jobname = ""
        email = ""
        method_submission = "web"

    isValidSubmitDate = True
    try:
        submit_date = datetime.strptime(submit_date_str, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        isValidSubmitDate = False
    current_time = datetime.now()

    resultdict['isResultFolderExist'] = True
    resultdict['errinfo'] = myfunc.ReadFile(errfile)

    status = ""
    queuetime = ""
    runtime = ""
    if not os.path.exists(rstdir):
        resultdict['isResultFolderExist'] = False
        resultdict['isFinished'] = False
        resultdict['isFailed'] = True
        resultdict['isStarted'] = False
    elif os.path.exists(failtagfile):
        resultdict['isFinished'] = False
        resultdict['isFailed'] = True
        resultdict['isStarted'] = True
        status = "Failed"
        start_date_str = myfunc.ReadFile(starttagfile).strip()
        isValidStartDate = True
        isValidFailedDate = True
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            isValidStartDate = False
        failed_date_str = myfunc.ReadFile(failtagfile).strip()
        try:
            failed_date = datetime.strptime(failed_date_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            isValidFailedDate = False
        if isValidSubmitDate and isValidStartDate:
            queuetime = myfunc.date_diff(submit_date, start_date)
        if isValidStartDate and isValidFailedDate:
            runtime = myfunc.date_diff(start_date, failed_date)
    else:
        resultdict['isFailed'] = False
        if os.path.exists(finishtagfile):
            resultdict['isFinished'] = True
            resultdict['isStarted'] = True
            status = "Finished"
            isValidStartDate = True
            isValidFinishDate = True
            start_date_str = myfunc.ReadFile(starttagfile).strip()
            try:
                start_date = datetime.strptime(start_date_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                isValidStartDate = False
            finish_date_str = myfunc.ReadFile(finishtagfile).strip()
            try:
                finish_date = datetime.strptime(finish_date_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                isValidFinishDate = False
            if isValidSubmitDate and isValidStartDate:
                queuetime = myfunc.date_diff(submit_date, start_date)
            if isValidStartDate and isValidFinishDate:
                runtime = myfunc.date_diff(start_date, finish_date)
        else:
            resultdict['isFinished'] = False
            if os.path.exists(starttagfile):
                isValidStartDate = True
                start_date_str = myfunc.ReadFile(starttagfile).strip()
                try:
                    start_date = datetime.strptime(start_date_str, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    isValidStartDate = False
                resultdict['isStarted'] = True
                status = "Running"
                if isValidSubmitDate and isValidStartDate:
                    queuetime = myfunc.date_diff(submit_date, start_date)
                if isValidStartDate:
                    runtime = myfunc.date_diff(start_date, current_time)
            else:
                resultdict['isStarted'] = False
                status = "Wait"
                if isValidSubmitDate:
                    queuetime = myfunc.date_diff(submit_date, current_time)

    color_status = SetColorStatus(status)

    file_seq_warning = "%s/%s/%s/%s"%(SITE_ROOT, "static/result", jobid, "query.warn.txt")
    seqwarninfo = ""
    if os.path.exists(file_seq_warning):
        seqwarninfo = myfunc.ReadFile(file_seq_warning)

    resultdict['file_seq_warning'] = os.path.basename(file_seq_warning)
    resultdict['seqwarninfo'] = seqwarninfo
    resultdict['jobid'] = jobid
    resultdict['jobname'] = jobname
    resultdict['outpathname'] = os.path.basename(outpathname)
    resultdict['resultfile'] = os.path.basename(resultfile)
    resultdict['tarball'] = os.path.basename(tarball)
    resultdict['zipfile'] = os.path.basename(zipfile)
    resultdict['submit_date'] = submit_date_str
    resultdict['queuetime'] = queuetime
    resultdict['runtime'] = runtime
    resultdict['BASEURL'] = BASEURL
    resultdict['status'] = status
    resultdict['color_status'] = color_status
    resultdict['nummodel'] = nummodel
    resultdict['query_seqfile'] = os.path.basename(query_seqfile)
    if os.path.exists(raw_query_seqfile):
        resultdict['raw_query_seqfile'] = os.path.basename(raw_query_seqfile)
    else:
        resultdict['raw_query_seqfile'] = ""
    resultdict['raw_query_modelfile'] = os.path.basename(raw_query_modelfile)
    base_www_url = "http://" + request.META['HTTP_HOST']
#   note that here one must add http:// in front of the url
    resultdict['url_result'] = "%s/pred/result/%s"%(base_www_url, jobid)

    sum_run_time = 0.0
    average_run_time = 120.0  # default average_run_time
    num_finished = 0
    cntnewrun = 0
    cntcached = 0
# get seqid_index_map
    if os.path.exists(finished_model_file):
        resultdict['index_table_header'] = ["ModelNo.", "Length", "RunTime(s)",
                "ProQ2", "ProQ_Lowres", "ProQ_Highres", "ProQ3"]
        index_table_content_list = []
        indexmap_content = myfunc.ReadFile(finished_model_file).split("\n")
        cnt = 0
        set_seqidx = set([])
        for line in indexmap_content:
            strs = line.split("\t")
            if len(strs)>=7:
                subfolder = strs[0]
                if not subfolder in set_seqidx:
                    length_str = strs[1]
                    try:
                        runtime_in_sec_str = "%.1f"%(float(strs[2]))
                    except:
                        runtime_in_sec_str = ""
                    try:
                        s_proq2 = "%.3f"%(float(strs[3]))
                    except:
                        s_proq2 = ""
                    try:
                        s_proqlowres = "%.3f"%(float(strs[4]))
                    except:
                        s_proqlowres = ""
                    try:
                        s_proqhighres = "%.3f"%(float(strs[5]))
                    except:
                        s_proqhighres = ""
                    try:
                        s_proq3 = "%.3f"%(float(strs[6]))
                    except:
                        s_proq3 = ""
                    rank = "%d"%(cnt)
                    index_table_content_list.append([rank, length_str,
                        runtime_in_sec_str, s_proq2, s_proqlowres,
                        s_proqhighres, s_proq3])
                    cnt += 1
                    set_seqidx.add(subfolder)
        if cntnewrun > 0:
            average_run_time = sum_run_time / cntnewrun

        resultdict['index_table_content_list'] = index_table_content_list
        resultdict['indexfiletype'] = "finishedfile"
        resultdict['num_finished'] = cnt
        num_finished = cnt
        resultdict['percent_finished'] = "%.1f"%(float(cnt)/nummodel*100)
    else:
        resultdict['index_table_header'] = []
        resultdict['index_table_content_list'] = []
        resultdict['indexfiletype'] = "finishedfile"
        resultdict['num_finished'] = 0
        resultdict['percent_finished'] = "%.1f"%(0.0)

    num_remain = nummodel - num_finished

    time_remain_in_sec = nummodel * 120 # set default value

    if os.path.exists(starttagfile):
        start_date_str = myfunc.ReadFile(starttagfile).strip()
        isValidStartDate = False
        try:
            start_date_epoch = datetime.strptime(start_date_str, "%Y-%m-%d %H:%M:%S").strftime('%s')
            isValidStartDate = True
        except:
            pass
        if isValidStartDate:
            time_now = time.time()
            runtime_total_in_sec = float(time_now) - float(start_date_epoch)
            cnt_torun = nummodel - cntcached #

            if cntnewrun <= 0:
                time_remain_in_sec = cnt_torun * 120
            else:
                time_remain_in_sec = int ( runtime_total_in_sec/float(cntnewrun)*cnt_torun+ 0.5)

    time_remain = myfunc.second_to_human(time_remain_in_sec)
    resultdict['time_remain'] = time_remain


    base_refresh_interval = 5 # seconds
    if nummodel <= 1:
        if method_submission == "web":
            resultdict['refresh_interval'] = base_refresh_interval
        else:
            resultdict['refresh_interval'] = base_refresh_interval
    else:
        #resultdict['refresh_interval'] = numseq * 2
        addtime = int(math.sqrt(max(0,min(num_remain, num_finished))))+1
        resultdict['refresh_interval'] = base_refresh_interval + addtime

    # get stat info
    if os.path.exists(statfile):#{{{
        content = myfunc.ReadFile(statfile)
        lines = content.split("\n")
        for line in lines:
            strs = line.split()
            if len(strs) >= 2:
                resultdict[strs[0]] = strs[1]
                percent =  "%.1f"%(int(strs[1])/float(numseq)*100)
                newkey = strs[0].replace('num_', 'per_')
                resultdict[newkey] = percent
#}}}
    dumped_resultfile = "%s/%s/%s"%(rstdir, jobid, "query.proq3.txt")


    resultdict['jobcounter'] = GetJobCounter(client_ip, isSuperUser,
            divided_logfile_query, divided_logfile_finished_jobid)
    return render(request, 'pred/get_results.html', resultdict)
#}}}
def get_results_eachseq(request, jobid="1", seqindex="1"):#{{{
    resultdict = {}

    resultdict['isAllNonTM'] = True

    username = request.user.username
    client_ip = request.META['REMOTE_ADDR']
    if username in settings.SUPER_USER_LIST:
        isSuperUser = True
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "submitted_seq.log")
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log", "finished_job.log")
    else:
        isSuperUser = False
        divided_logfile_query =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_submitted_seq.log"%(client_ip))
        divided_logfile_finished_jobid =  "%s/%s/%s"%(SITE_ROOT,
                "static/log/divided", "%s_finished_job.log"%(client_ip))

    resultdict['username'] = username
    resultdict['isSuperUser'] = isSuperUser
    resultdict['client_ip'] = client_ip

    rstdir = "%s/%s"%(path_result, jobid)
    outpathname = jobid

    jobinfofile = "%s/jobinfo"%(rstdir)
    jobinfo = myfunc.ReadFile(jobinfofile).strip()
    jobinfolist = jobinfo.split("\t")
    if len(jobinfolist) >= 8:
        submit_date_str = jobinfolist[0]
        numseq = int(jobinfolist[3])
        jobname = jobinfolist[5]
        email = jobinfolist[6]
        method_submission = jobinfolist[7]
    else:
        submit_date_str = ""
        numseq = 1
        jobname = ""
        email = ""
        method_submission = "web"

    status = ""

    resultdict['jobid'] = jobid
    resultdict['jobname'] = jobname
    resultdict['outpathname'] = os.path.basename(outpathname)
    resultdict['BASEURL'] = BASEURL
    resultdict['status'] = status
    resultdict['numseq'] = numseq
    base_www_url = "http://" + request.META['HTTP_HOST']

    resultfile = "%s/%s/%s/%s"%(rstdir, outpathname, seqindex, "query_topologies.txt")
    if os.path.exists(resultfile):
        resultdict['resultfile'] = os.path.basename(resultfile)
    else:
        resultdict['resultfile'] = ""



    # get topology for the first seq
    topfolder_seq0 = "%s/%s/%s"%(rstdir, jobid, seqindex)
    subdirname = seqindex
    resultdict['subdirname'] = subdirname
    nicetopfile = "%s/nicetop.html"%(topfolder_seq0)
    if os.path.exists(nicetopfile):
        resultdict['nicetopfile'] = "%s/%s/%s/%s/%s"%(
                "result", jobid, jobid, subdirname,
                os.path.basename(nicetopfile))
    else:
        resultdict['nicetopfile'] = ""
    resultdict['isResultFolderExist'] = False
    if os.path.exists(topfolder_seq0):
        resultdict['isResultFolderExist'] = True
        topolist = []
        TMlist = []
        methodlist = ['BOCTOPUS2']
        for i in xrange(len(methodlist)):
            color = "#000000"
            seqid = ""
            seqanno = ""
            top = ""
            method = methodlist[i]
            if method == "BOCTOPUS2":
                topfile = "%s/query_topologies.txt"%(topfolder_seq0)
                color = "#000000"
            if os.path.exists(topfile):
                (seqid, seqanno, top) = myfunc.ReadSingleFasta(topfile)
            else:
                top = ""

            if method == "Homology":
                if seqid != "":
                    resultdict['showtext_homo'] = seqid
                    resultdict['pdbcode_homo'] = seqid[:4].lower()
                else:
                    resultdict['showtext_homo'] = "PDB-homology"
                    resultdict['pdbcode_homo'] = ""

            posTM = myfunc.GetTMPosition_boctopus2(top)
            posSP = []
            if len(posSP) > 0:
                posSP_str = "%d-%d"%(posSP[0][0]+1, posSP[0][1]+1)
            else:
                posSP_str = ""
            topolist.append([method, top])
            newPosTM = ["%d-%d"%(x+1,y+1) for x,y in posTM]
            if posSP_str == "" and len(newPosTM) == 0:
                if method == "Homology":
                    newPosTM = ["***No homologous TM proteins detected***"]
                else:
                    newPosTM = ["***No TM-regions predicted***"]
            else:
                resultdict['isAllNonTM'] = False
            TMlist.append([method, color, posSP_str, newPosTM])

        resultdict['topolist'] = topolist
        resultdict['TMlist'] = TMlist

    resultdict['jobcounter'] = GetJobCounter(client_ip, isSuperUser,
            divided_logfile_query, divided_logfile_finished_jobid)
    return render(request, 'pred/get_results_eachseq.html', resultdict)
#}}}


def my_view(request):#{{{
    # loop through keys
    for key in request.POST:
        value = request.POST[key]
    # loop through keys and values
    for key, value in request.POST.iteritems():
        print key, value
#}}}
def search_form(request):#{{{
    return render(request, 'pred/search_form.html')
#}}}


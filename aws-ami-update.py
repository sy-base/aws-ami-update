#!/usr/bin/python
import os, sys, getopt, time
import boto3
from botocore import exceptions

#########################################################
VERSION="1.0"
#########################################################
## Begin Function Definitions
#########################################################
# Define Global defaults
DEBUG=False
DebugLevel = 0
TestRun=False
AwsSession = None
Ec2Client = None
DefaultProfileName = None
DefaultAwsConfigFile=None
DefaultAwsRegion = "us-east-1"
UpdateAMI_SourceLaunchPermissions = []
UpdateAMI_UserDataFile = "userdata.txt"
UpdateAMI_Ec2UserData = ""
##### Default Shutdown commands
# Immediate Shutdown
UpdateAMI_ShutdownCMD = """/sbin/halt -n"""
# Delayed Shutdown
#UpdateAMI_ShutdownCMD = """echo "/sbin/halt -n" | /usr/bin/at now + 1 minute"""
##################################################
def show_usage():
    print("""
Usage: aws-ami-update.py [options] -a <Source Ami Id> -n <Ami Name>
  -h --help                             Show this help
  -v --version                          Show version
  -a --aws-id=<Ami Id>                  Specify Ami Id for source image (i.e. ami-14c5486b)                 [REQUIRED]
  -n --name=<Ami Name>                  Specify Name of new Ami                                             [REQUIRED]
  -p --profile-name=<profile name>      Specify alternate aws authentication profile                        [Default: default]
  -c --config=<config file>             Specify alternate aws client config file                            [Default: ~/.aws/config]
  -l --log-file                         Specify file location to write log                                  [NOT IMPLEMENTED]`
  -r --region=<Aws Region>              Specify Aws Region (i.e. us-west-2)                                 [Default: us-east-1]
  -u --userdata-file=<UserData File>    Specify Userdata file to execute on ami
  -m --mirror-launchpermissions         Mirror source AMI launch permissions
  -i --instance-type                    Specify Aws instance type (i.e. t2-micro)                           [NOT IMPLEMENTED]
  -d --debug                            Enable Debug logging or increase debug level
  -t --testrun                          Enable TestRun mode (AWS DryRun, takes no action)
     --no-shutdown                      Skip addition of shutdown command to Userdata
     --log-instance-console             Output transient ec2 console to log
     --wait-interval                    Interval between checking AMI/Instance status during provisioning   [NOT IMPLEMENTED]
     --wait-timeout                     Maximum time to wait for AMI/Instance steps during provisioning     [NOT IMPLEMENTED]
     --mail-to=<Email Address>          Send email notification to listed email addresses                   [NOT IMPLEMENTED]

""")
    sys.exit(411)

def show_version():
    print('aws-ami-update.py version {0}'.format(VERSION))
    sys.exit(411)

def LOGMSG(LogMsg,LogLvl='INFO',DebugMsgLvl=1):
    if (LogLvl == 'DEBUG' and DEBUG):
        if DebugLevel >= DebugMsgLvl:
            print(":{0}:{1}:{2}:{3}".format(Timestamp(),LogLvl,DebugMsgLvl,LogMsg))
    elif (LogLvl == 'INFO'):
        print(":{0}:{1}::{2}".format(Timestamp(),LogLvl,LogMsg))
    elif (LogLvl == 'ERROR'):
        print(":{0}:{1}::{2}".format(Timestamp(),LogLvl,LogMsg))
    else:
        return 0
    return 0
def DEBUG1MSG(DebugMsg,DebugMsgLvl=1):
    print(":{0}:{1}:DEBUG:{2}".format(Timestamp(),DebugMsgLvl,DebugMsg))
    return 0

def Timestamp():
    currtime = time.strftime("%m/%d/%Y %H:%M:%S %Z")
    return currtime
    
def ValidateRegion(AwsRegion):
    AwsRegionNames = ['us-east-1','us-east-2','us-west-1','us-west-2','ap-northeast-1','ap-northeast-2','ap-south-1','ap-southeast-1','ap-southeast-2','ca-central-1','cn-northwest-1','eu-central-1','eu-west-1','eu-west-2','eu-west-3','sa-east-1']
    if AwsRegion in AwsRegionNames:
        return True
    else:
        return False
    return None

def InitAwsSession(AwsConfigFile=DefaultAwsConfigFile,ProfileName=DefaultProfileName,AwsRegion=DefaultAwsRegion,AKID=None,SAK=None):
    if (AwsConfigFile is not None):
        os.environ["AWS_CONFIG_FILE"] = AwsConfigFile
        os.environ["AWS_SHARED_CREDENTIALS_FILE"] = ""

    
    LOGMSG('InitAwsSession.AwsConfigFile: {0}'.format(AwsConfigFile),'DEBUG',1)
    LOGMSG('InitAwsSession.ProfileName: {0}'.format(ProfileName),'DEBUG',1)
    LOGMSG('InitAwsSession.AwsRegion: {0}'.format(AwsRegion),'DEBUG',1)

    aws = boto3.Session (
        aws_access_key_id=AKID,
        aws_secret_access_key=SAK,
        region_name=AwsRegion,
        profile_name=ProfileName
    )
    try:
        ec2 = aws.client('ec2')
        TestResponse = ec2.describe_account_attributes(
            AttributeNames=[
                'default-vpc',
            ],
            DryRun=False
        )
        LOGMSG('InitAwsSession.TestResponse: {0}'.format(TestResponse),DEBUG,3)
    except exceptions.NoCredentialsError:
        LOGMSG('Unable to locate valid credentials','ERROR')
        sys.exit(1)
    except exceptions.ClientError as err:
        ExceptionReturn = BotoExceptionHandling(err)
        if (ExceptionReturn == 1):
            sys.exit(2)
        elif (ExceptionReturn == 2):
            LOGMSG('Authentication Failure','ERROR')
            sys.exit(2)
        else:
            raise err
    return [aws, ec2]
    

def BotoExceptionHandling(err):
    if err.response['Error']['Code'] == 'DryRunOperation':
        return 0
    elif err.response['Error']['Code'] == 'InvalidAMIID.NotFound':
        LOGMSG('ami id not found, verify ami id and aws region.','ERROR')
        return 1
    elif err.response['Error']['Code'] == 'AuthFailure':
        return 2
    else:
        raise err
    return 99

def GetIAM_CurrentUser():
    global AwsSession
    iam = AwsSession.client('iam')
    response = iam.get_user()
    LOGMSG('GetIAM_CurrentUser.reponse[User][UserName]: {0}'.format(response['User']['UserName']),'DEBUG',2)
    return response['User']['UserName']

def ReadUserDataFile(UserDataFile="userdata.txt"):
    Ec2UserData = ""
    
    try:
        Ec2UserData_fh = open(UserDataFile)
        Ec2UserData_lines = ["#!/bin/bash"]
        for Ec2UserData_line in Ec2UserData_fh:
            if Ec2UserData_line != "":
                Ec2UserData_lines.append(Ec2UserData_line)
        Ec2UserData_lines.append(UpdateAMI_ShutdownCMD)
    finally:
        Ec2UserData_fh.close()
    
    Ec2UserData = '\n'.join(Ec2UserData_lines)
    LOGMSG('ReadUserDataFile.Ec2UserData: >>>\n{0}'.format(Ec2UserData),'DEBUG',2)
    LOGMSG('ReadUserDataFile.Ec2UserData: <<<END','DEBUG',2)
    return Ec2UserData

def Verify_AMI(AwsAmiId,AwsRegion=DefaultAwsRegion,MirrorLaunchPermissions=False):
    LaunchPermissions=None
    if(not AwsAmiId.startswith("ami-")):
        LOGMSG('Invalid AMI id, AMI Ids begin with ami- prefix.','ERROR')
        show_usage()
    LOGMSG('Verify_AMI.AwsAmiId: {0}'.format(AwsAmiId),'DEBUG',3)
    LOGMSG('Verify_AMI.AwsRegion: {0}'.format(AwsRegion),'DEBUG',3)
    #ec2_udata = UpdateAMI_Ec2UserData

    # Retrieve image launchPermissions
    if (MirrorLaunchPermissions):
        try:
            AmiAttributes = Ec2Client.describe_image_attribute(
                Attribute='launchPermission',
                ImageId=AwsAmiId,
                DryRun=False,
            )
            # Read image launcPermissions
            #global UpdateAMI_SourceLaunchPermissions
            #UpdateAMI_SourceLaunchPermissions = AmiAttributes['LaunchPermissions']
            LaunchPermissions = AmiAttributes['LaunchPermissions']
            LOGMSG('Verify_AMI.UpdateAMI_SourceLaunchPermissions: {0}'.format(LaunchPermissions),'DEBUG',2)
        except exceptions.ClientError as err:
            ExceptionReturn = BotoExceptionHandling(err)
            if (ExceptionReturn is 1):
                sys.exit(1)
            elif (ExceptionReturn is 2):
                #LaunchPemission access denied can be caused by using AWS provided image as source
                LOGMSG('Unable to mirror Launch Permissions. Access Denied.','WARN')
            else:
                sys.exit(ExceptionReturn)

    # DryRun of Ec2 Launch
    try:
        response = Ec2Client.run_instances(
            ImageId=AwsAmiId,
            InstanceType='t2.micro',
            DryRun=True,
            InstanceInitiatedShutdownBehavior='stop',
            MinCount=1,
            MaxCount=1,
        )
    except exceptions.ClientError as err:
        ExceptionReturn = BotoExceptionHandling(err)
        if (ExceptionReturn is 0):
            response = 0
            return [response, LaunchPermissions]
        elif (ExceptionReturn is 1):
            sys.exit(1)
        elif (ExceptionReturn is 2):
            LOGMSG('Authentication Failure','ERROR')
            sys.exit(1)
        else:
            sys.exit(ExceptionReturn)
    return [98, None]

def Create_Ec2(AwsAmiId,AwsRegion=DefaultAwsRegion,Ec2UserData=UpdateAMI_Ec2UserData,TestRun=True):
    LOGMSG('Create_Ec2.AwsAmiId: {0}'.format(AwsAmiId),'DEBUG',3)
    LOGMSG('Create_Ec2.AwsRegion: {0}'.format(AwsRegion),'DEBUG',3)
    
    debug_Ec2UserData = """#!/bin/bash
/usr/bin/yum -y update
echo "/sbin/halt -n" | /usr/bin/at now + 1 minute"""
    LOGMSG('Create_Ec2.Ec2UserData: >>>\n{0}'.format(Ec2UserData),'DEBUG',3)
    LOGMSG('Create_Ec2.Ec2UserData: <<<END','DEBUG',3)
    try:
        AwsCurrentUserName = GetIAM_CurrentUser()
        LOGMSG('Create_Ec2.AwsCurrentUserName: {0}'.format(AwsCurrentUserName),'DEBUG',3)
        response = Ec2Client.run_instances(
            ImageId=AwsAmiId,
            InstanceType='t2.micro',
            DryRun=TestRun,
            InstanceInitiatedShutdownBehavior='stop',
            MinCount=1,
            MaxCount=1,
            TagSpecifications=[
                {
                    'ResourceType': 'instance',
                    'Tags': [
                        {
                            'Key': 'OwnerUserName',
                            'Value': AwsCurrentUserName,
                        },
                        {
                            'Key': 'Name',
                            'Value': 'Aws-Ami-Update Transient Instance',
                        },
                    ]
                },
            ],
            UserData=Ec2UserData,
        )
    except exceptions.ClientError as err:
        ExceptionReturn = BotoExceptionHandling(err)
        if (ExceptionReturn == 1):
            sys.exit(2)
        elif (ExceptionReturn == 2):
            LOGMSG('Authentication Failure','ERROR')
            sys.exit(2)
    if (TestRun is False):
        LOGMSG(response,'DEBUG',4)
        Ec2InstanceState = response['Instances'][0]['State']['Code']
        Ec2InstanceStateDesc = response['Instances'][0]['State']['Name']
        Ec2InstanceId = response['Instances'][0]['InstanceId']
        LOGMSG('Create_Ec2.Ec2InstanceVpcId: {0}'.format(response['Instances'][0]['VpcId']),'DEBUG',2)
        LOGMSG('Create_Ec2.Ec2InstanceSubnetId: {0}'.format(response['Instances'][0]['SubnetId']),'DEBUG',2)
        LOGMSG('Create_Ec2.Ec2InstanceState: {0}'.format(str(Ec2InstanceState)),'DEBUG',1)
        LOGMSG('Create_Ec2.Ec2InstanceStateDesc: {0}'.format(Ec2InstanceStateDesc),'DEBUG',1)
        LOGMSG('Create_Ec2.Ec2InstanceId: {0}'.format(Ec2InstanceId),'DEBUG',1)
#        LOGMSG('Create_Ec2.Ec2InstancePublicDnsName: {0}'.format(response['Instances'][0]['PublicDnsName'])
#        LOGMSG('Create_Ec2.Ec2InstancePublicIpAddress: {0}'.format(response['Instances'][0]['PublicIpAddress'])
        return {'Ec2InstanceState':str(Ec2InstanceState), 'Ec2InstanceId':str(Ec2InstanceId), }
    else:
        return {'Ec2InstanceState':str('1'), 'Ec2InstanceId':str(0), }
    return {'Ec2InstanceState':str(99), 'Ec2InstanceId':str(0), }

def Terminate_Ec2(Ec2InstanceId, AwsRegion, PreserveLog=False, TestRun=True):
    LOGMSG('Terminate_Ec2.Ec2InstanceId: {0}'.format(Ec2InstanceId),'DEBUG',1)
    LOGMSG('Terminate_Ec2.AwsRegion: {0}'.format(AwsRegion),'DEBUG',2)
    if (PreserveLog):
        try:
            response = Ec2Client.get_console_output(
                InstanceId=Ec2InstanceId,
                DryRun=False
            )
        except exceptions.ClientError as err:
            ExceptionReturn = BotoExceptionHandling(err)
            if (ExceptionReturn is 1):
                sys.exit(2)
            elif (ExceptionReturn is 2):
                LOGMSG('Authentication Failure','ERROR')
                sys.exit(2)
        ConsoleLog=response['Output']
        LOGMSG('Terminate_Ec2.ConsoleLog.Ouput: <<<\n{0}'.format(ConsoleLog))
        LOGMSG('Terminate_EC2.ConsoleLog.Output: <<<END')
    try:
        response = Ec2Client.terminate_instances(
            InstanceIds=[
                Ec2InstanceId,
            ],
            DryRun=TestRun,
        )
    except exceptions.ClientError as err:
        ExceptionReturn = BotoExceptionHandling(err)
        if (ExceptionReturn is 1):
            sys.exit(2)
        elif (ExceptionReturn is 2):
            LOGMSG('Authentication Failure','ERROR')
            sys.exit(2)
    if (TestRun is False):
        Ec2InstanceState = response['TerminatingInstances'][0]['CurrentState']['Code']
        Ec2InstanceStateDesc = response['TerminatingInstances'][0]['CurrentState']['Name']
        Ec2InstancePrevState = response['TerminatingInstances'][0]['PreviousState']['Code']
        Ec2InstancePrevStateDesc = response['TerminatingInstances'][0]['PreviousState']['Name']
        Ec2InstanceId = response['TerminatingInstances'][0]['InstanceId']
        LOGMSG('Terminate_Ec2.Ec2InstancePrevState: {0}'.format(str(Ec2InstancePrevState)),'DEBUG',3)
        LOGMSG('Terminate_Ec2.Ec2InstancePrevStateDesc: {0}'.format(Ec2InstancePrevStateDesc),'DEBUG',3)
        LOGMSG('Terminate_Ec2.Ec2InstanceState: {0}'.format(str(Ec2InstanceState)),'DEBUG',2)
        LOGMSG('Terminate_Ec2.Ec2InstanceStateDesc: {0}'.format(Ec2InstanceStateDesc),'DEBUG',2)
        LOGMSG('Terminate_Ec2.Ec2InstanceId: {0}'.format(Ec2InstanceId),'DEBUG',2)
        return {'Ec2InstanceState':str(Ec2InstanceState), 'Ec2InstanceId':str(Ec2InstanceId), }
    else:
        return {'Ec2InstanceState':str('1'), 'Ec2InstanceId':str(0), }
    return {'Ec2InstanceState':str(99), 'Ec2InstanceId':str(0), }    

def WaitInstanceState(Ec2InstanceId, AwsRegion, Ec2InstanceStateCode, Ec2DesiredInstanceStateCode=80, WaitInstanceStateLoopInterval=60, WaitInstanceStateTimeout=900, TestRun=False):
    #### Instance State Codes
    #  0: pending
    # 16: running
    # 32: shutting-down
    # 48: terminated
    # 64: stopping
    # 80: stopped
    ####
    if (TestRun):
        return 99
    if (not Ec2InstanceId.startswith("i-")):
        return 99

    WaitInstanceStateLoopTime = 0
    while WaitInstanceStateLoopTime <= WaitInstanceStateTimeout:        
        response = Ec2Client.describe_instance_status(
            InstanceIds=[
                Ec2InstanceId,
            ],
            DryRun=TestRun,
            IncludeAllInstances=True
        )
        Ec2ResponseInstanceId = response['InstanceStatuses'][0]['InstanceId']
        Ec2InstanceStateCode = response['InstanceStatuses'][0]['InstanceState']['Code']
        Ec2InstanceStateName = response['InstanceStatuses'][0]['InstanceState']['Name']
        if Ec2InstanceStateCode == Ec2DesiredInstanceStateCode:
            LOGMSG('WaitInstanceState.Ec2InstanceId: {0}'.format(Ec2InstanceId),'DEBUG',2)
            LOGMSG('WaitInstanceState.Ec2ResponseInstanceId: {0}'.format(Ec2ResponseInstanceId),'DEBUG',3)
            LOGMSG('WaitInstanceState.Ec2StateCode: {0}'.format(Ec2InstanceStateCode),'DEBUG',2)
            LOGMSG('WaitInstanceState.Ec2StateName: {0}'.format(Ec2InstanceStateName),'DEBUG',2)
            LOGMSG('InstanceId {0} is {1}.'.format(Ec2InstanceId, Ec2InstanceStateName))
            return 0
        else:
            LOGMSG('WaitInstanceState.WaitInstanceStateLoopTime: {0}'.format(WaitInstanceStateLoopTime),'DEBUG',1)
            LOGMSG('WaitInstanceState.WaitInstanceStateTimeout: {0}'.format(WaitInstanceStateTimeout),'DEBUG',1)
            LOGMSG('WaitInstanceState.Ec2InstanceId: {0}'.format(Ec2InstanceId),2)
            LOGMSG('WaitInstanceState.Ec2ResponseInstanceId: {0}'.format(Ec2ResponseInstanceId),'DEBUG',3)
            LOGMSG('WaitInstanceState.Ec2StateCode: {0}'.format(Ec2InstanceStateCode),'DEBUG',2)
            LOGMSG('WaitInstanceState.Ec2StateName: {0}'.format(Ec2InstanceStateName),'DEBUG',2)
            LOGMSG('InstanceId {0} is {1}.'.format(Ec2InstanceId, Ec2InstanceStateName))
            LOGMSG('Waiting {0} seconds for instance state change...'.format(WaitInstanceStateLoopInterval))
            time.sleep(WaitInstanceStateLoopInterval)
            WaitInstanceStateLoopTime += WaitInstanceStateLoopInterval
    else:
        LOGMSG('Timeout exceeded waiting for instance','ERROR')
        sys.exit(3)
    return 98

def WaitAmiState(AwsAmiId, AwsRegion, DesiredAmiStateName='available', WaitAmiStateLoopInterval=30, WaitAmiStateTimeout=600, TestRun=False):
    if (TestRun):
        return 99
    if (not AwsAmiId.startswith("ami-")):
        return 98
    else:
        LOGMSG('New AMI Id: {0}'.format(AwsAmiId))

    WaitAmiStateLoopTime = 0
    while WaitAmiStateLoopTime <= WaitAmiStateTimeout:
        response = Ec2Client.describe_images(
            ImageIds=[
                AwsAmiId,
            ],
            DryRun=TestRun
        )
        ResponseAmiId = response['Images'][0]['ImageId']
        DesiredAmiStateName="available"
        AmiStateName = response['Images'][0]['State']
        if AmiStateName == DesiredAmiStateName:
            LOGMSG('WaitAmiState.AwsAmiId: {0}'.format(AwsAmiId),'DEBUG',2)
            LOGMSG('WaitAmiState.ResponseAmiId: {0}'.format(ResponseAmiId),'DEBUG',3)
            LOGMSG('WaitAmiState.AmiStateName: {0}.'.format(AmiStateName),'DEBUG',2)
            LOGMSG('Ami Id {0} is {1}.'.format(ResponseAmiId, AmiStateName))
            return 0
        else:
            LOGMSG('WaitAmiState.WaitAmiStateLoopTime: {0}'.format(WaitAmiStateLoopTime),'DEBUG',1)
            LOGMSG('WaitAmiState.WaitAmiStateTimeout: {0}'.format(WaitAmiStateTimeout),'DEBUG',1)
            LOGMSG('WaitAmiState.AwsAmiId: {0}'.format(AwsAmiId),'DEBUG',2)
            LOGMSG('WaitAmiState.ResponseAmiId: {0}'.format(ResponseAmiId),'DEBUG',3)
            LOGMSG('WaitAmiState.AmiStateName: {0}.'.format(AmiStateName),'DEBUG',2)
            LOGMSG('WaitAmiState.DesiredAmiStateName: {0}.'.format(DesiredAmiStateName),'DEBUG',2)
            LOGMSG('Ami Id {0} is {1}.'.format(ResponseAmiId, AmiStateName))
            LOGMSG('Waiting {0} seconds for Ami state change...'.format(WaitAmiStateLoopInterval))
            time.sleep(WaitAmiStateLoopInterval)
            WaitAmiStateLoopTime += WaitAmiStateLoopInterval
    else:
        LOGMSG('Timeout exceeded waiting for Ami creation','ERROR')
        sys.exit(5)
    return 98

def Create_AMI(Ec2InstanceId,AmiName,AwsRegion=DefaultAwsRegion,LaunchPermissions=None,TestRun=False):
    AmiSuffix = Ec2InstanceId.split('-')
    AmiName = AmiName + " " + AmiSuffix[1]
    if (TestRun):
        return 99
    if (not Ec2InstanceId.startswith("i-")):
        return 98

    try:
        response = Ec2Client.create_image(
            Description='',
            DryRun=TestRun,
            InstanceId=Ec2InstanceId,
            Name=AmiName,
            NoReboot=True,
        )
    except exceptions.ClientError as err:
        raise err
    NewAwsAmiId = response['ImageId']
    LOGMSG('Create_AMI.NewAwsAmiId: {0}'.format(NewAwsAmiId),'DEBUG',2)
    return NewAwsAmiId

def main(argv):
    # Set Defaults annd Read in Arguments
    AwsRegion = DefaultAwsRegion
    AwsAmiId = None
    AwsAmiName = None
    AwsConfigFile = DefaultAwsConfigFile
    ProfileName = DefaultProfileName
    UserDataFile = UpdateAMI_UserDataFile
    AccessKeyId = None
    SecretAccessKey = None
    MirrorLaunchPermissions = False
    PreserveLog = False

    try:
        if (len(argv) == 0):
            show_usage()
        opts, args = getopt.getopt(argv,"hvtdmc:p:u:r:a:n:",["help","version","testrun","debug","mirror-launchpermissions","log-instance-console","config=","profile-name=","userdata-file=","no-shutdown","region=","ami-id=","ami-name=","access-key-id=","secret-access-key=",])
    except getopt.GetoptError as opterr:
        LOGMSG(opterr,'ERROR')
        show_usage()
    for opt, arg in opts:
        if opt in ("-h", "--help"):
            show_usage()
        if opt in ("-v", "--version"):
            show_version()
        elif opt in ("-t", "--testrun"):
            global TestRun
            TestRun = True
            LOGMSG("TestRun mode: Enabled")
        elif opt in ("-d", "--debug"):
            global DEBUG, DebugLevel
            DEBUG = True
            DebugLevel += 1
            if (DebugLevel == 1):
                LOGMSG("Debug mode: Enabled")
        elif opt == '--no-shutdown':
            global UpdateAMI_ShutdownCMD
            UpdateAMI_ShutdownCMD = ""
        elif opt in ("-m", "--mirror-launchpermissions"):
            MirrorLaunchPermissions=True
        elif opt == '--log-instance-console':
            PreserveLog=True
        elif opt in ("-r", "--region"):
            AwsRegion = arg.lower()
            ValidRegion = ValidateRegion(AwsRegion)
            if (not ValidRegion):
                LOGMSG('Invalid region specified','ERROR')
                sys.exit(97)
        elif opt in ("-c", "--config"):
            AwsConfigFile = arg
            if (not os.path.isfile(AwsConfigFile)):
                LOGMSG('Alternate Aws client configuration not found.','ERROR')
                sys.exit(1)
        elif opt in ("-p", "--profile-name"):
           ProfileName = arg
        elif opt in ("-a", "--ami-id"):
            AwsAmiId = arg
        elif opt in ("-n", "--ami-name"):
            AwsAmiName = arg
        elif opt in ("-u", "--userdata-file"):
            ##Read Userdata file into UserDataFile
            UserDataFile = arg
        elif opt == '--access-key-id':
            AccessKeyId = arg
        elif opt == '--secret-access-key':
            SecretAccessKey = arg
    if(AwsAmiId is None):
        print('Ami Id is required.\n')
        show_usage()
    if (AwsAmiName is None):
        print('Ami Name is required.\n')
        show_usage()
    
    global AwsSession, Ec2Client
    AwsSession,Ec2Client = InitAwsSession(AwsConfigFile, ProfileName, AwsRegion, AccessKeyId, SecretAccessKey)
    # Begin main
    LOGMSG('Updating AWS Image Id: {0}'.format(AwsAmiId))
    LOGMSG('New AMI Name: {0}'.format(AwsAmiName))
    LOGMSG('main.AwsRegion: {0}'.format(AwsRegion),'DEBUG',1)
    UpdateAMI_Ec2UserData = ReadUserDataFile(UserDataFile)
    LOGMSG('Update execution will be as follows: >>>')
    print(UpdateAMI_Ec2UserData)
    LOGMSG('<<<END')
    VerifyAMIReturn,LaunchPermissions = Verify_AMI(AwsAmiId,AwsRegion,MirrorLaunchPermissions)
    LOGMSG('main.LaunchPermissions: {0}'.format(LaunchPermissions),'DEBUG',1)
    if(VerifyAMIReturn == 98):
        LOGMSG('An unkown error occurred while verifying source Ami','ERROR')
        sys.exit(1)
    if (VerifyAMIReturn != 0):
        sys.exit(1)
    CreateEc2Return = Create_Ec2(AwsAmiId,AwsRegion,UpdateAMI_Ec2UserData,TestRun)
    if (CreateEc2Return['Ec2InstanceState'] == str('1')):
        LOGMSG('CreateEc2Return.TestRunComplete','DEBUG',1)
        LOGMSG('Test Run Complete')
        sys.exit(0)
    LOGMSG('main.CreateEc2Return.Ec2InstanceState: {0}'.format(CreateEc2Return['Ec2InstanceState']),'DEBUG',1)
    LOGMSG('main.CreateEc2Return.Ec2InstanceId: {0}'.format(CreateEc2Return['Ec2InstanceId']),'DEBUG',1)
    WaitInstanceStateReturn = WaitInstanceState(CreateEc2Return['Ec2InstanceId'], AwsRegion, CreateEc2Return['Ec2InstanceState'])
    LOGMSG('main.WaitInstanceStateReturn: {0}'.format(WaitInstanceStateReturn),'DEBUG',1)
    if WaitInstanceStateReturn == 99:
        LOGMSG('main.WaitInstanceStateReturn.TestRunComplete','DEBUG',1)
        LOGMSG("Test Run Complete")
        sys.exit(0)
    elif WaitInstanceStateReturn == 98:
        LOGMSG('An unkown error occurred, exiting','ERROR')
        sys.exit(3)
    ## CreateAMI
    CreateAmiReturn = Create_AMI(CreateEc2Return['Ec2InstanceId'], AwsAmiName, AwsRegion, LaunchPermissions)
    LOGMSG('main.CreateAmiReturn: {0}'.format(CreateAmiReturn),1)
    if (CreateAmiReturn == 98):
        LOGMSG('Ami creation failed with an unknown error','ERROR')
        sys.exit(4)
    NewAwsAmiId = CreateAmiReturn
    WaitAmiStateReturn = WaitAmiState(NewAwsAmiId, AwsRegion)
    if (WaitAmiStateReturn == 99):
        LOGMSG('main.WaitAmiStateReturn.Testcomplete','DEBUG',1)
        sys.exit(0)
    elif (WaitAmiStateReturn == 98):
        LOGMSG('Failed while waiting for Ami creation to complete','ERROR')
        sys.exit(5)
    elif (WaitAmiStateReturn == 0):
        if (LaunchPermissions is not None and len(LaunchPermissions) >= 1):
            try:
                response = Ec2Client.modify_image_attribute(
                    Attribute='launchPermission',
                    ImageId=NewAwsAmiId,
                    LaunchPermission={
                        'Add': LaunchPermissions,
                    },
                    OperationType='add',
                )
            except exceptions.ClientError as err:
                raise err
            LOGMSG('main.Create_AMI.modify_image_attribute.response: {0}'.format(response),'DEBUG',4)
    
        LOGMSG('Ami creation completed successfully')
        
        ## Terminate Ec2 Instance
        TerminateEc2Return = Terminate_Ec2(CreateEc2Return['Ec2InstanceId'], AwsRegion, PreserveLog, TestRun)
        if (TerminateEc2Return['Ec2InstanceState'] == str('1')):
            LOGMSG('TerminateEc2Return.TestRunComplete')
            LOGMSG('Test Run Complete')
            sys.exit(0)
        LOGMSG('main.TerminateEc2Return.Ec2InstanceId: {0}'.format(TerminateEc2Return['Ec2InstanceId']),'DEBUG',2)
        LOGMSG('main.TerminateEc2Return.Ec2InstanceState: {0}'.format(TerminateEc2Return['Ec2InstanceState']),'DEBUG',2)
        WaitInstanceStateReturn = WaitInstanceState(TerminateEc2Return['Ec2InstanceId'], AwsRegion, TerminateEc2Return['Ec2InstanceState'], 48, 15, 300)
        LOGMSG('main.TerminateEc2.WaitInstanceStateReturn: {0}'.format(WaitInstanceStateReturn),'DEBUG',2)
        if WaitInstanceStateReturn == 99:
            LOGMSG('WaitInstanceStateReturn.TestRunComplete','DEBUG',1)
            LOGMSG('Test Run Complete')
            sys.exit(0)
        elif WaitInstanceStateReturn == 98:
            LOGMSG('An unkown error occurred, exiting','ERROR')
            sys.exit(7)
        elif WaitInstanceStateReturn == 0:
            LOGMSG('Transient Ec2 Instance Terminated')

    else:
        LOGMSG('Unknown error occurred while waiting for Ami creation.','ERROR')
        sys.exit(5)
    
    return 0
################################################## 
### End Function Definitions
##################################################

if __name__ == "__main__":
    main(sys.argv[1:])
    sys.exit(0)


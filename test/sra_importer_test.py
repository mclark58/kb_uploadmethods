# -*- coding: utf-8 -*-
import unittest
import os  # noqa: F401
import json  # noqa: F401
import time
import requests
import shutil
from mock import patch
import hashlib

from os import environ
try:
    from ConfigParser import ConfigParser  # py2
except:
    from configparser import ConfigParser  # py3

from pprint import pprint  # noqa: F401

from biokbase.workspace.client import Workspace as workspaceService
from kb_uploadmethods.kb_uploadmethodsImpl import kb_uploadmethods
from kb_uploadmethods.kb_uploadmethodsServer import MethodContext
from kb_uploadmethods.Utils.ImportSRAUtil import ImportSRAUtil
from DataFileUtil.DataFileUtilClient import DataFileUtil


class kb_uploadmethodsTest(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.token = environ.get('KB_AUTH_TOKEN', None)
        cls.user_id = requests.post(
            'https://kbase.us/services/authorization/Sessions/Login',
            data='token={}&fields=user_id'.format(cls.token)).json()['user_id']
        # WARNING: don't call any logging methods on the context object,
        # it'll result in a NoneType error
        cls.ctx = MethodContext(None)
        cls.ctx.update({'token': cls.token,
                        'user_id': cls.user_id,
                        'provenance': [
                            {'service': 'kb_uploadmethods',
                             'method': 'please_never_use_it_in_production',
                             'method_params': []
                             }],
                        'authenticated': 1})
        config_file = environ.get('KB_DEPLOYMENT_CONFIG', None)
        cls.cfg = {}
        config = ConfigParser()
        config.read(config_file)
        for nameval in config.items('kb_uploadmethods'):
            cls.cfg[nameval[0]] = nameval[1]
        cls.wsURL = cls.cfg['workspace-url']
        cls.wsClient = workspaceService(cls.wsURL, token=cls.token)
        cls.serviceImpl = kb_uploadmethods(cls.cfg)
        cls.dfu = DataFileUtil(os.environ['SDK_CALLBACK_URL'], token=cls.token)
        cls.scratch = cls.cfg['scratch']
        cls.shockURL = cls.cfg['shock-url']

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, 'wsName'):
            cls.wsClient.delete_workspace({'workspace': cls.wsName})
            print('Test workspace was deleted')

    @classmethod
    def make_ref(self, objinfo):
        return str(objinfo[6]) + '/' + str(objinfo[0]) + '/' + str(objinfo[4])

    @classmethod
    def delete_shock_node(cls, node_id):
        header = {'Authorization': 'Oauth {0}'.format(cls.token)}
        requests.delete(cls.shockURL + '/node/' + node_id, headers=header,
                        allow_redirects=True)
        print('Deleted shock node ' + node_id)

    def getWsClient(self):
        return self.__class__.wsClient

    def getWsName(self):
        if hasattr(self.__class__, 'wsName'):
            return self.__class__.wsName
        suffix = int(time.time() * 1000)
        wsName = "test_kb_uploadmethods_" + str(suffix)
        ret = self.getWsClient().create_workspace({'workspace': wsName})  # noqa
        self.__class__.wsName = wsName
        return wsName

    def getImpl(self):
        return self.__class__.serviceImpl

    def getContext(self):
        return self.__class__.ctx

    def check_lib(self, lib, size, filename, md5):
        shock_id = lib["file"]["id"]
        print "LIB: {}".format(str(lib))
        print "Shock ID: {}".format(str(shock_id))
        fileinput = [{
                    'shock_id': shock_id,
                    'file_path': self.scratch + '/temp',
                    'unpack': 'uncompress'}]
        print "File Input: {}".format(str(fileinput))
        files = self.dfu.shock_to_file_mass(fileinput)
        path = files[0]["file_path"]
        file_md5 = hashlib.md5(open(path, 'rb').read()).hexdigest()
        libfile = lib['file']
        self.assertEqual(file_md5, md5)
        self.assertEqual(lib['size'], size)
        self.assertEqual(lib['type'], 'fq')
        self.assertEqual(lib['encoding'], 'ascii')

        self.assertEqual(libfile['file_name'], filename)
        self.assertEqual(libfile['hid'].startswith('KBH_'), True)

        self.assertEqual(libfile['type'], 'shock')
        self.assertEqual(libfile['url'], self.shockURL)

    def mock_download_staging_file(params):
        print 'Mocking DataFileUtilClient.download_staging_file'
        print params

        fq_filename = params.get('staging_file_subdir_path')
        fq_path = os.path.join('/kb/module/work/tmp', fq_filename)
        shutil.copy(os.path.join("data", fq_filename), fq_path)

        return {'copy_file_path': fq_path}

    def mock_validate_upload_staging_file_availability(staging_file_subdir_path):
        print 'Mocking ImportSRAUtil._validate_upload_staging_file_availability'
        print staging_file_subdir_path

    def mock_run_command_pe(command):
        print 'Mocking ImportSRAUtil._run_command'

        tmp_dir = command.split(' ')[-2]
        scratch_sra_file_path = command.split(' ')[-1]

        sra_name = os.path.basename(scratch_sra_file_path).partition('.')[0]

        fwd_file_path = os.path.join(tmp_dir, sra_name, '1')
        os.makedirs(fwd_file_path)
        rev_file_path = os.path.join(tmp_dir, sra_name, '2')
        os.makedirs(rev_file_path)

        fwd_filename = 'small.forward.fq'
        shutil.copy(os.path.join("data", fwd_filename), fwd_file_path)
        os.rename(os.path.join(fwd_file_path, fwd_filename), os.path.join(fwd_file_path, 'fastq'))

        rev_filename = 'small.reverse.fq'
        shutil.copy(os.path.join("data", rev_filename), rev_file_path)
        os.rename(os.path.join(rev_file_path, rev_filename), os.path.join(rev_file_path, 'fastq'))

    def mock_run_command_se(command):
        print 'Mocking ImportSRAUtil._run_command'

        tmp_dir = command.split(' ')[-2]
        scratch_sra_file_path = command.split(' ')[-1]

        sra_name = os.path.basename(scratch_sra_file_path).partition('.')[0]

        fwd_file_path = os.path.join(tmp_dir, sra_name)
        os.makedirs(fwd_file_path)

        fq_filename = 'Sample1.fastq'
        shutil.copy(os.path.join("data", fq_filename), fwd_file_path)
        os.rename(os.path.join(fwd_file_path, fq_filename), os.path.join(fwd_file_path, 'fastq'))

    def test_bad_import_genbank_from_staging_params(self):
        invalidate_input_params = {
          'missing_staging_file_subdir_path': 'staging_file_subdir_path',
          'sequencing_tech': 'sequencing_tech',
          'name': 'name',
          'workspace_name': 'workspace_name'
        }
        with self.assertRaisesRegexp(
                    ValueError,
                    '"staging_file_subdir_path" parameter is required, but missing'):
            self.getImpl().import_sra_from_staging(self.getContext(), invalidate_input_params)

        invalidate_input_params = {
          'staging_file_subdir_path': 'staging_file_subdir_path',
          'missing_sequencing_tech': 'sequencing_tech',
          'name': 'name',
          'workspace_name': 'workspace_name'
        }
        with self.assertRaisesRegexp(
                    ValueError,
                    '"sequencing_tech" parameter is required, but missing'):
            self.getImpl().import_sra_from_staging(self.getContext(), invalidate_input_params)

        invalidate_input_params = {
          'staging_file_subdir_path': 'staging_file_subdir_path',
          'sequencing_tech': 'sequencing_tech',
          'missing_name': 'name',
          'workspace_name': 'workspace_name'
        }
        with self.assertRaisesRegexp(
                ValueError,
                '"name" parameter is required, but missing'):
            self.getImpl().import_sra_from_staging(self.getContext(), invalidate_input_params)

        invalidate_input_params = {
          'staging_file_subdir_path': 'staging_file_subdir_path',
          'sequencing_tech': 'sequencing_tech',
          'name': 'name',
          'missing_workspace_name': 'workspace_name'
        }
        with self.assertRaisesRegexp(
                ValueError,
                '"workspace_name" parameter is required, but missing'):
            self.getImpl().import_sra_from_staging(self.getContext(), invalidate_input_params)

    @patch.object(DataFileUtil, "download_staging_file", side_effect=mock_download_staging_file)
    @patch.object(ImportSRAUtil, "SRA_TOOLKIT_PATH", new='/kb/module/work/tmp/fastq-dump')
    @patch.object(ImportSRAUtil, "_validate_upload_staging_file_availability",
                  side_effect=mock_validate_upload_staging_file_availability)
    @patch.object(ImportSRAUtil, "_run_command", side_effect=mock_run_command_pe)
    def test_import_sra_paired_end(self, download_staging_file,
                                   _validate_upload_staging_file_availability,
                                   _run_command):

        sra_path = 'empty.sra'
        obj_name = 'MyReads'

        params = {
            'staging_file_subdir_path': sra_path,
            'name': obj_name,
            'workspace_name': self.getWsName(),
            'sequencing_tech': 'Unknown',
            'single_genome': 0,
            'insert_size_mean': 99.9,
            'insert_size_std_dev': 10.1,
            'read_orientation_outward': 1
        }

        ref = self.getImpl().import_sra_from_staging(self.getContext(), params)
        self.assertTrue('obj_ref' in ref[0])
        self.assertTrue('report_ref' in ref[0])
        self.assertTrue('report_name' in ref[0])

        obj = self.dfu.get_objects(
            {'object_refs': [self.getWsName() + '/MyReads']})['data'][0]
        self.assertEqual(ref[0]['obj_ref'], self.make_ref(obj['info']))
        self.assertEqual(obj['info'][2].startswith(
            'KBaseFile.PairedEndLibrary'), True)

        d = obj['data']
        file_name = d["lib1"]["file"]["file_name"]
        self.assertTrue(file_name.endswith(".inter.fastq.gz"))
        self.assertEqual(d['sequencing_tech'], 'Unknown')
        self.assertEqual(d['single_genome'], 0)
        self.assertEqual('source' not in d, True)
        self.assertEqual('strain' not in d, True)
        self.assertEqual(d['interleaved'], 1)
        self.assertEqual(d['read_orientation_outward'], 1)
        self.assertEqual(d['insert_size_mean'], 99.9)
        self.assertEqual(d['insert_size_std_dev'], 10.1)
        self.check_lib(d['lib1'], 2491520, file_name,
                       '1c58d7d59c656db39cedcb431376514b')
        node = d['lib1']['file']['id']
        self.delete_shock_node(node)

    @patch.object(DataFileUtil, "download_staging_file", side_effect=mock_download_staging_file)
    @patch.object(ImportSRAUtil, "SRA_TOOLKIT_PATH", new='/kb/module/work/tmp/fastq-dump')
    @patch.object(ImportSRAUtil, "_validate_upload_staging_file_availability",
                  side_effect=mock_validate_upload_staging_file_availability)
    @patch.object(ImportSRAUtil, "_run_command", side_effect=mock_run_command_se)
    def test_import_sra_single_end(self, download_staging_file,
                                   _validate_upload_staging_file_availability,
                                   _run_command):

        sra_path = 'empty.sra'
        obj_name = 'MyReads'

        params = {
            'staging_file_subdir_path': sra_path,
            'name': obj_name,
            'workspace_name': self.getWsName(),
            'sequencing_tech': 'Unknown',
            'single_genome': 1
        }

        ref = self.getImpl().import_sra_from_staging(self.getContext(), params)
        self.assertTrue('obj_ref' in ref[0])
        self.assertTrue('report_ref' in ref[0])
        self.assertTrue('report_name' in ref[0])

        obj = self.dfu.get_objects(
            {'object_refs': [self.getWsName() + '/MyReads']})['data'][0]
        self.assertEqual(ref[0]['obj_ref'], self.make_ref(obj['info']))
        self.assertEqual(obj['info'][2].startswith(
            'KBaseFile.SingleEndLibrary'), True)
        d = obj['data']
        self.assertEqual(d['sequencing_tech'], 'Unknown')
        self.assertEqual(d['single_genome'], 1)
        self.assertEqual('source' not in d, True)
        self.assertEqual('strain' not in d, True)
        self.check_lib(d['lib'], 2833, 'fastq.fastq.gz',
                       'f118ee769a5e1b40ec44629994dfc3cd')
        node = d['lib']['file']['id']
        self.delete_shock_node(node)

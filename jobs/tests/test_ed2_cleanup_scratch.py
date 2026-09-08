import gzip
from pathlib import Path
import tempfile
import unittest
from jobs.tools.ed2_cleanup_scratch import cleanup,digest

class CleanupTests(unittest.TestCase):
    def test_preserves_science_and_binaries_removes_only_build_source(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);work=root/'work';art=root/'artefacts'
            (work/'src').mkdir(parents=True);(work/'build'/'CMakeFiles').mkdir(parents=True)
            (art/'source').mkdir(parents=True);(root/'inputs').mkdir()
            keep={art/'source'/'children.jnnw':b'children',art/'models-sealed.json':b'seal',
                  work/'train-native.tsv':b'table',work/'RESULTS.txt':b'logs',root/'inputs'/'data':b'input'}
            for path,data in keep.items():path.write_bytes(data)
            for i in range(20):(work/'src'/str(i)).write_bytes(b'code')
            binary=work/'build'/'jass_ed2_value_probe';binary.write_bytes(b'native-binary')
            before=digest(binary)
            (work/'build'/'CMakeFiles'/'CMakeOutput.log').write_text('diagnostic')
            r=cleanup(work,art)
            self.assertFalse((work/'src').exists());self.assertFalse((work/'build').exists())
            self.assertEqual(r['removed']['src']['files'],20)
            self.assertEqual(r['retained_binaries']['jass_ed2_value_probe']['sha256'],before)
            self.assertEqual(gzip.decompress((art/'build-outputs'/'jass_ed2_value_probe.gz').read_bytes()),b'native-binary')
            self.assertEqual((art/'build-outputs'/'logs'/'CMakeFiles'/'CMakeOutput.log').read_text(),'diagnostic')
            for path,data in keep.items():self.assertEqual(path.read_bytes(),data)
            self.assertEqual(cleanup(work,art),r)

    def test_refuses_cross_root_artifact_before_deleting_anything(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);work=root/'work';art=root/'other';(work/'src').mkdir(parents=True);art.mkdir()
            with self.assertRaises(ValueError):cleanup(work,art)
            self.assertTrue((work/'src').is_dir())

    def test_refuses_symlinked_scratch_and_preserves_external_file(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);work=root/'work';art=root/'artefacts';outside=root/'outside'
            work.mkdir();art.mkdir();outside.mkdir();(outside/'protected').write_text('keep')
            (work/'src').symlink_to(outside,target_is_directory=True)
            with self.assertRaises(ValueError):cleanup(work,art)
            self.assertEqual((outside/'protected').read_text(),'keep')

if __name__=='__main__':unittest.main()

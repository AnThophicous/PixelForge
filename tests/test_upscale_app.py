import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from PIL import Image

from upscale_app import UpscaleOptions, ask_laya, load_dotenv, model_fits_output, upscale_image


class UpscaleTests(unittest.TestCase):
    def test_quality_backend_writes_requested_size(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "source.png"
            output = root / "output.png"
            Image.new("RGB", (17, 11), (20, 40, 80)).save(source)
            backend = upscale_image(source, output, UpscaleOptions(scale=3, mode="quality"))
            self.assertEqual(backend, "quality")
            with Image.open(output) as result:
                self.assertEqual(result.size, (51, 33))

    def test_rejects_same_input_and_output(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "same.png"
            Image.new("RGB", (4, 4)).save(path)
            with self.assertRaises(ValueError):
                upscale_image(path, path, UpscaleOptions())

    def test_dotenv_reads_only_laya_key(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text("LAYA_KEY=abc\nOTHER=ignore\n", encoding="utf-8")
            self.assertEqual(load_dotenv(path), {"LAYA_KEY": "abc"})

    def test_laya_uses_metadata_and_returns_typed_choice(self):
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self, limit):
                return b'{"answers":{"mode":{"choice":"quality"}}}'

        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "source.png"
            Image.new("RGB", (17, 11), (20, 40, 80)).save(source)
            with patch("upscale_app.urllib.request.build_opener") as build_opener:
                build_opener.return_value.open.return_value = Response()
                self.assertEqual(ask_laya(source, 4, "test-key"), "quality")
                request = build_opener.return_value.open.call_args.args[0]
                self.assertEqual(request.full_url, "https://wire.ia.br/v1/decide")
                self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
                self.assertNotIn(str(source), request.data.decode("utf-8"))

    def test_model_resolution_limits(self):
        self.assertTrue(model_fits_output(Path("EDSR_x4.pb"), 400, 500, 4))
        self.assertFalse(model_fits_output(Path("EDSR_x4.pb"), 600, 600, 4))
        self.assertTrue(model_fits_output(Path("FSRCNN_x4.pb"), 900, 1000, 4))
        self.assertFalse(model_fits_output(Path("ESPCN_x4.pb"), 1100, 1100, 4))


if __name__ == "__main__":
    unittest.main()

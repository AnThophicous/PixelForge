package com.brenno.pixelforge

import android.content.ContentValues
import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import android.provider.MediaStore
import org.opencv.android.Utils
import org.opencv.core.Mat
import org.opencv.core.Size
import org.opencv.dnn_superres.DnnSuperResImpl
import org.opencv.imgproc.Imgproc
import java.io.File
import androidx.media3.common.MediaItem
import androidx.media3.effect.ScaleAndRotateTransformation
import androidx.media3.transformer.Composition
import androidx.media3.transformer.EditedMediaItem
import androidx.media3.transformer.Effects
import androidx.media3.transformer.ExportException
import androidx.media3.transformer.ExportResult
import androidx.media3.transformer.Transformer
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

private const val MODEL_SCALE = 4

class ImageUpscaler(private val context: Context) {
    fun process(uri: Uri, requestedScale: Int) {
        val bitmap = context.contentResolver.openInputStream(uri).use { BitmapFactory.decodeStream(it) }
            ?: error("Não foi possível ler a imagem")
        val mat = Mat()
        Utils.bitmapToMat(bitmap, mat)
        val model = loadModel("FSRCNN_x4.pb", "fsrcnn")
        val output = Mat()
        model.upsample(mat, output)
        val requestedWidth = bitmap.width * requestedScale
        val requestedHeight = bitmap.height * requestedScale
        val capped = capToLongEdge(output, 4096)
        val target = resizeToTarget(capped, requestedWidth, requestedHeight)
        val result = Bitmap.createBitmap(target.cols(), target.rows(), Bitmap.Config.ARGB_8888)
        Utils.matToBitmap(target, result)
        saveImage(result, uri.lastPathSegment ?: "image")
        mat.release(); output.release(); capped.release(); target.release(); bitmap.recycle(); result.recycle()
    }

    private fun loadModel(name: String, algorithm: String): DnnSuperResImpl {
        val path = copyAsset(name)
        return DnnSuperResImpl.create().apply { readModel(path); setModel(algorithm, MODEL_SCALE) }
    }

    private fun copyAsset(name: String): String {
        val output = File(context.cacheDir, name)
        if (!output.exists()) context.assets.open("models/$name").use { input -> output.outputStream().use(input::copyTo) }
        return output.absolutePath
    }

    private fun capToLongEdge(input: Mat, maxEdge: Int): Mat {
        val edge = maxOf(input.cols(), input.rows())
        if (edge <= maxEdge) return input
        val ratio = maxEdge.toDouble() / edge
        val result = Mat()
        Imgproc.resize(input, result, Size(input.cols() * ratio, input.rows() * ratio), 0.0, 0.0, Imgproc.INTER_AREA)
        return result
    }

    private fun resizeToTarget(input: Mat, width: Int, height: Int): Mat {
        val ratio = minOf(1.0, 4096.0 / maxOf(width, height))
        val targetWidth = (width * ratio).toInt().coerceAtLeast(1)
        val targetHeight = (height * ratio).toInt().coerceAtLeast(1)
        if (input.cols() == targetWidth && input.rows() == targetHeight) return input
        val result = Mat()
        Imgproc.resize(input, result, Size(targetWidth.toDouble(), targetHeight.toDouble()), 0.0, 0.0, Imgproc.INTER_AREA)
        return result
    }

    private fun saveImage(bitmap: Bitmap, name: String) {
        val values = ContentValues().apply {
            put(MediaStore.Images.Media.DISPLAY_NAME, "PixelForge_${name.substringBeforeLast('.')}.png")
            put(MediaStore.Images.Media.MIME_TYPE, "image/png")
            put(MediaStore.Images.Media.RELATIVE_PATH, "Pictures/PixelForge")
        }
        val uri = context.contentResolver.insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values) ?: error("Não foi possível criar a saída")
        context.contentResolver.openOutputStream(uri).use { bitmap.compress(Bitmap.CompressFormat.PNG, 100, it) }
    }
}

class VideoUpscaler(private val context: Context) {
    suspend fun process(uri: Uri, requestedScale: Int) {
        val output = File(context.cacheDir, "pixelforge_video_${System.nanoTime()}.mp4")
        val scale = requestedScale.coerceIn(2, 4).toFloat()
        val item = EditedMediaItem.Builder(MediaItem.fromUri(uri))
            .setEffects(Effects(emptyList(), listOf(ScaleAndRotateTransformation.Builder().setScale(scale, scale).build())))
            .build()
        suspendCancellableCoroutine<Unit> { continuation ->
            val transformer = Transformer.Builder(context)
                .addListener(object : Transformer.Listener {
                    override fun onCompleted(composition: Composition, exportResult: ExportResult) {
                        continuation.resume(Unit)
                    }

                    override fun onError(composition: Composition, exportResult: ExportResult, exportException: ExportException) {
                        continuation.resumeWithException(exportException)
                    }
                })
                .build()
            transformer.start(item, output.absolutePath)
            continuation.invokeOnCancellation { transformer.cancel() }
        }
        saveVideo(output, uri.lastPathSegment ?: "video")
        output.delete()
    }

    private fun saveVideo(source: File, name: String) {
        val values = ContentValues().apply {
            put(MediaStore.Video.Media.DISPLAY_NAME, "PixelForge_${name.substringBeforeLast('.')}.mp4")
            put(MediaStore.Video.Media.MIME_TYPE, "video/mp4")
            put(MediaStore.Video.Media.RELATIVE_PATH, "Movies/PixelForge")
        }
        val uri = context.contentResolver.insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, values) ?: error("Não foi possível criar a saída")
        context.contentResolver.openOutputStream(uri).use { output -> source.inputStream().use { input -> input.copyTo(output!!) } }
    }
}

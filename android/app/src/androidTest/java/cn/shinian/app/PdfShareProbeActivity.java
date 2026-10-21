package cn.shinian.app;

import android.app.Activity;
import android.os.Bundle;
import android.os.Message;
import android.os.Messenger;
import android.os.Process;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;

/** Separate test-APK UID; Java keeps this process independent of the target APK's Kotlin runtime. */
public final class PdfShareProbeActivity extends Activity {
    @Override
    @SuppressWarnings("deprecation")
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        Messenger reply = getIntent().getParcelableExtra("reply");
        Bundle result = new Bundle();
        result.putInt("uid", Process.myUid());
        try (InputStream input = getContentResolver().openInputStream(getIntent().getData());
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            if (input == null) throw new IllegalStateException("No PDF stream");
            byte[] buffer = new byte[8192];
            int length;
            while ((length = input.read(buffer)) != -1) output.write(buffer, 0, length);
            result.putByteArray("bytes", output.toByteArray());
        } catch (Exception error) {
            result.putString("error", error.getClass().getName());
        }
        try {
            Message message = Message.obtain();
            message.setData(result);
            if (reply != null) reply.send(message);
        } catch (android.os.RemoteException error) {
            throw new IllegalStateException(error);
        } finally {
            finish();
        }
    }
}

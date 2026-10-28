package top.momowhale.music;
import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import java.security.KeyStore;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;
import java.nio.charset.StandardCharsets;
import org.json.JSONObject;
public final class SecureConfig {
 private static final String ALIAS="whale-music-connection-v1";
 private static SecretKey key() throws Exception {
  KeyStore store=KeyStore.getInstance("AndroidKeyStore");store.load(null);
  if(!store.containsAlias(ALIAS)){KeyGenerator g=KeyGenerator.getInstance("AES","AndroidKeyStore");g.init(new KeyGenParameterSpec.Builder(ALIAS,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT).setBlockModes("GCM").setEncryptionPaddings("NoPadding").setKeySize(256).build());g.generateKey();}
  return (SecretKey)store.getKey(ALIAS,null);
 }
 public static void save(Context context,String raw) throws Exception {
  ConnectionConfig base=new ConnectionConfig(raw);JSONObject root=new JSONObject(raw);
  if(root.has("roomControl")){ConnectionConfig room=new ConnectionConfig(root.getJSONObject("roomControl").toString());if(!room.host.equals(base.host)||!room.knownHost.equals(base.knownHost)||!"whale-room-control".equals(room.user))throw new IllegalArgumentException("房间连接配置不正确");}
  Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.ENCRYPT_MODE,key());
  String iv=Base64.encodeToString(c.getIV(),Base64.NO_WRAP),data=Base64.encodeToString(c.doFinal(raw.getBytes(StandardCharsets.UTF_8)),Base64.NO_WRAP);
  if(!context.getSharedPreferences("connection",0).edit().putString("sealed",iv+":"+data).commit())throw new IllegalStateException("连接配置保存失败");
 }
 private static String loadRaw(Context context) throws Exception {
  String value=context.getSharedPreferences("connection",0).getString("sealed",null);if(value==null)return null;
  String[] p=value.split(":",2);Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,Base64.decode(p[0],Base64.NO_WRAP)));
  return new String(c.doFinal(Base64.decode(p[1],Base64.NO_WRAP)),StandardCharsets.UTF_8);
 }
 public static ConnectionConfig load(Context context) throws Exception {String raw=loadRaw(context);return raw==null?null:new ConnectionConfig(raw);}
 public static ConnectionConfig loadRoom(Context context) throws Exception {String raw=loadRaw(context);if(raw==null)return null;JSONObject root=new JSONObject(raw);return root.has("roomControl")?new ConnectionConfig(root.getJSONObject("roomControl").toString()):null;}
 public static void clear(Context context){context.getSharedPreferences("connection",0).edit().clear().apply();}
}

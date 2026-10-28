package top.momowhale.music;
import org.json.JSONObject;
public final class ConnectionConfig {
 public final String host,user,knownHost,privateKey; public final int port;
 public ConnectionConfig(String raw) throws Exception {
  if(raw.length()>16384)throw new IllegalArgumentException("连接文件过大");
  JSONObject j=new JSONObject(raw);if(j.getInt("version")!=1)throw new IllegalArgumentException("连接文件版本不支持");
  host=j.getString("host");user=j.getString("user");port=j.optInt("port",22);knownHost=j.getString("knownHost");privateKey=j.getString("privateKey");
  if(!host.matches("[A-Za-z0-9.-]{1,253}")||!user.matches("[a-z][a-z0-9-]{0,31}")||port!=22||knownHost.length()>2000||!knownHost.startsWith(host+" ecdsa-sha2-nistp256 ")||!privateKey.startsWith("-----BEGIN RSA PRIVATE KEY-----"))throw new IllegalArgumentException("连接文件格式不正确");
 }
}

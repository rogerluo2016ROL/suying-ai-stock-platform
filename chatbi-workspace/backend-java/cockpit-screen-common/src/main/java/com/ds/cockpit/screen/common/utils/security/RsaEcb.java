package com.ds.cockpit.screen.common.utils.security;


import org.apache.commons.lang3.ArrayUtils;

import javax.crypto.Cipher;
import java.security.KeyFactory;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Base64;

/**
 * RSA/ECB/PKCS1Padding算法
 */
public class RsaEcb {

	// MAX_DECRYPT_BLOCK应等于密钥长度/8（1byte=8bit），所以当密钥位数为2048时，最大解密长度应为256.
	private static final String RSA_ALGORITHM = "RSA/ECB/PKCS1Padding";

	/**
	 * RSA最大加密明文大小
	 */
	private static final int MAX_ENCRYPT_BLOCK = 117;
	/**
	 * RSA最大解密密文大小
	 */
	private static final int MAX_DECRYPT_BLOCK = 256;
	// 不仅可以使用DSA算法，同样也可以使用RSA算法做数字签名
	private static final String KEY_ALGORITHM = "RSA";
	// 编码格式
	private static final String CODE_FORMATE_UTF8 = "UTF-8";

	/**
	 * RSA 公钥加密，【不限制长度】
	 *
	 * @param str       加密字符串
	 * @param publicKey 公钥
	 * @return 密文
	 */
	public static String encryptByPublicKey(String str, String publicKey) throws Exception {
		// base64编码的公钥
		byte[] keyBytes = Base64.getDecoder().decode(publicKey);
		RSAPublicKey pubKey = (RSAPublicKey) KeyFactory.getInstance(KEY_ALGORITHM).generatePublic(new X509EncodedKeySpec(keyBytes));
		// RSA加密
		// 安卓这里有坑，换成下面这种RSA/ECB/PKCS1Padding可行
		// Cipher cipher = Cipher.getInstance(KEY_ALGORITHM);
		Cipher cipher = Cipher.getInstance(RSA_ALGORITHM);

		cipher.init(Cipher.ENCRYPT_MODE, pubKey);

		byte[] data = str.getBytes(CODE_FORMATE_UTF8);
		// 加密时超过117字节就报错。为此采用分段加密的办法来加密
		byte[] enBytes = null;
		for (int i = 0; i < data.length; i += MAX_ENCRYPT_BLOCK) {
			// 注意要使用2的倍数，否则会出现加密后的内容再解密时为乱码
			byte[] doFinal = cipher.doFinal(ArrayUtils.subarray(data, i, i + MAX_ENCRYPT_BLOCK));
			enBytes = ArrayUtils.addAll(enBytes, doFinal);
		}
		String outStr = Base64.getEncoder().encodeToString(enBytes);
		return outStr;
	}

	/**
	 * RSA 私钥解密，【不限制长度】
	 *
	 * @param encryStr   加密字符串
	 * @param privateKey 私钥
	 * @return 明文
	 */
	public static String decryptByPrivateKey(String encryStr, String privateKey) throws Exception {
		// base64编码的私钥
		byte[] decoded = Base64.getDecoder().decode(privateKey);
		RSAPrivateKey priKey = (RSAPrivateKey) KeyFactory.getInstance(KEY_ALGORITHM).generatePrivate(new PKCS8EncodedKeySpec(decoded));
		// RSA解密
		// 安卓这里有坑，换成下面这种RSA/ECB/PKCS1Padding可行
		// Cipher cipher = Cipher.getInstance(KEY_ALGORITHM);
		Cipher cipher = Cipher.getInstance(RSA_ALGORITHM);

		cipher.init(Cipher.DECRYPT_MODE, priKey);

		// 64位解码加密后的字符串
		byte[] data = Base64.getDecoder().decode(encryStr);
		// 解密时超过128字节报错。为此采用分段解密的办法来解密
		StringBuilder sb = new StringBuilder();
		for (int i = 0; i < data.length; i += MAX_DECRYPT_BLOCK) {
			byte[] doFinal = cipher.doFinal(ArrayUtils.subarray(data, i, i + MAX_DECRYPT_BLOCK));
			sb.append(new String(doFinal));
		}
		return sb.toString();
	}
}

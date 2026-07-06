package com.ds.cockpit.screen.common.utils.security;

import java.util.Base64;

import javax.crypto.Cipher;
import javax.crypto.spec.IvParameterSpec;
import javax.crypto.spec.SecretKeySpec;

/**
 * AES/CBC/PKCS5Padding算法
 */
public final class AesCbc {
	/*
	 * 已确认 加密用的Key 可以用26个字母和数字组成 此处使用AES-128-CBC加密模式，key需要为16位。
	 */
	private static AesCbc instance = null;

	private AesCbc() {

	}

	public static AesCbc getInstance() {
		if (instance == null) {
			instance = new AesCbc();
		}
		return instance;
	}

	// 加密
	public static String encrypt(String sSrc, String sKey, String ivParameter) throws Exception {
		Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
		byte[] raw = sKey.getBytes();
		SecretKeySpec skeySpec = new SecretKeySpec(raw, "AES");
		IvParameterSpec iv = new IvParameterSpec(ivParameter.getBytes()); // 使用CBC模式，需要一个向量iv，可增加加密算法的强度
		cipher.init(Cipher.ENCRYPT_MODE, skeySpec, iv);
		byte[] encrypted = cipher.doFinal(sSrc.getBytes("utf-8"));
		return Base64.getEncoder().encodeToString(encrypted).replace("\n", ""); // 此处使用BASE64做转码。

	}

	// 解密
	public static String decryptToString(String sSrc, String sKey, String ivParameter) {
		try {
			byte[] raw = sKey.getBytes("ASCII");
			SecretKeySpec skeySpec = new SecretKeySpec(raw, "AES");
			Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
			IvParameterSpec iv = new IvParameterSpec(ivParameter.getBytes());
			cipher.init(Cipher.DECRYPT_MODE, skeySpec, iv);
			byte[] original = cipher.doFinal(Base64.getDecoder().decode(sSrc));
			String originalString = new String(original, "utf-8");
			return originalString;
		} catch (Exception ex) {
			return null;
		}
	}

	// 解密
	public static byte[] decrypt(String sSrc, String sKey, String ivParameter) {
		try {
			byte[] raw = sKey.getBytes("ASCII");
			SecretKeySpec skeySpec = new SecretKeySpec(raw, "AES");
			Cipher cipher = Cipher.getInstance("AES/CBC/PKCS5Padding");
			IvParameterSpec iv = new IvParameterSpec(ivParameter.getBytes());
			cipher.init(Cipher.DECRYPT_MODE, skeySpec, iv);
			byte[] original = cipher.doFinal(Base64.getDecoder().decode(sSrc));
			return original;
			/*String originalString = new String(original, "utf-8");
			return originalString;*/
		} catch (Exception ex) {
			return null;
		}
	}

}
package com.ds.cockpit.screen.common.utils.security;


import java.security.NoSuchAlgorithmException;
import java.util.Base64;

import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;

import cn.hutool.core.util.RandomUtil;


/**
 * aes秘钥生成器
 *
 */
public class AesKeyGenerator {
	public static final String DEFAULT_KEY = "ajgekbmgfkasefqk";
	public static final String AES_KEY_SALT_SEPERATOR = "@DS@";

	public static String createAesKey(boolean isDefault) {
		if (isDefault) {
			return DEFAULT_KEY;
		} else {
			return createAesKey();
		}
	}

	/**
	 * 生成AES密钥
	 *
	 * @return
	 */
	public static String createAesKey() {
		try {
			KeyGenerator kg = KeyGenerator.getInstance("AES");
			// 下面调用方法的参数决定了生成密钥的长度，可以修改为128, 192或256
			kg.init(192);
			SecretKey sk = kg.generateKey();
			byte[] b = sk.getEncoded();
			String secret = Base64.getEncoder().encodeToString(b);
			return secret;
		} catch (NoSuchAlgorithmException e) {
			e.printStackTrace();
			throw new RuntimeException("没有此算法");
		}
	}

	/**
	 * 生成AES密钥的盐值
	 *
	 * @return
	 */
	public static String createAesSalt() {
		return RandomUtil.randomString(16);
	}
}

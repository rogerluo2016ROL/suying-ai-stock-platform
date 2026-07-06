package com.ds.cockpit.screen.common.utils.security;

import lombok.Data;

/**
 * 加密对象模型
 *
 */
@Data
public class EncryptVo {
	private String encryptData;
	private String encryptKey;

	public String getEncryptData() {
		return encryptData;
	}

	public void setEncryptData(String encryptData) {
		this.encryptData = encryptData;
	}

	public String getEncryptKey() {
		return encryptKey;
	}

	public void setEncryptKey(String encryptKey) {
		this.encryptKey = encryptKey;
	}
}

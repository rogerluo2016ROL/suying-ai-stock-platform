package com.ds.cockpit.screen.web.controller.system;

import org.apache.commons.text.similarity.LevenshteinDistance;

/**
 * @Author: ZhouHong
 * @Date: 2025/8/14 08:58
 */
public class LevenshteinDemo {


    public static void main(String[] args) {
        String str1 = "埃安2025年7月销量";
        String str2 = "埃安2025年6月销量";
        LevenshteinDistance distance = new LevenshteinDistance();
        int edits = distance.apply(str1, str2);
        double similarity = 1 - (double)edits / Math.max(str1.length(), str2.length());
        System.out.println("相似度：" + similarity);
    }
}

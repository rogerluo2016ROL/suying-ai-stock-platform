<!--
 * @Author: zixin 
 * @Date: 2025-05-21 10:30:04
 * @LastEditors: zixin 
 * @LastEditTime: 2025-05-26 17:16:12
 * @FilePath: \cockpit-mobile-frontend\src\views\ai\module\feedback.vue
 * @Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
-->
<template>
  <div class="wrapper">
    <div class="flex justify-between align-center">
        <img src="@/assets/images/push/feed.png" alt="" class="">
        <div class="tishi">若是回答不符合您的预期，请留下您期望回答的内容吧!</div>
        <img src="@/assets/images/push/close.png" alt="" class="" @click="$emit('close')">
    </div>
    <div class="mt-3">
      <div class="mt-2">
        <div class="title font-13">针对问题</div>
        <div class="flex flex-wrap mt-1">
          <div v-for="item in questionList" :key="item" class="mr-1 font- mt-2"  :class="questionSelect.indexOf(item) > -1 ? 'active' : 'noactice'" @click="selectFun(item,1)">{{ item }}</div>
        </div>
      </div>
      <div class="mt-5">
        <div class="title font-13">针对回答</div>
        <div class="flex flex-wrap mt-1">
          <div v-for="item in answerList" :key="item" class="mr-1 font- mt-2"  :class="answerSelect.indexOf(item) > -1 ? 'active' : 'noactice'" @click="selectFun(item,2)">{{ item }}</div>
        </div>
      </div>
      <div class="mt-5">
        <div class="title font-13">我要补充</div>
        <div class="flex flex-wrap mt-1">
          <van-field
            v-model="message"
            rows="1"
            autosize
            label=""
            type="textarea"
            placeholder="写下更详细的情况"
            class="custom-field"
          />
        </div>
      </div>
    </div>

    <div class="btn">
      <div class="pb-3 font-13 text-center" style="color: #4B5563;">谢谢您宝贵的建议，我们会持续优化的!</div>
      <div class="submit" @click="submitFun">提交</div>
    </div>
  </div>
</template>

<script>
import {feedbackQ,feedbackA,feedbackSubmit } from "@/api/ai/ai.js";
export default {
  props:{
    row:{
      type:Object,
      default(){
        return {}
      }
    },
  },
  data() {
    return {
      questionList: [],
      answerList: [],
      questionSelect:[],
      answerSelect:[],
      message:''
    };
  },
   watch:{
    row:{
      immediate: true,
      handler(val){
        console.log(val);
        this.getformData(val)
      },
      deep:true
    }
  },
  methods: {
    getformData(val){
      feedbackQ(val).then(res=>{
        this.questionList = res.data
      })
      feedbackA(val).then(res=>{
        this.answerList = res.data
      })
    },
    selectFun(item,type){
      if(type == 1){
        let index = this.questionSelect.indexOf(item)
        if(index > -1){
          this.questionSelect.splice(index,1)
        }else{
          this.questionSelect.push(item)
        }
      }else{
        let index = this.answerSelect.indexOf(item)
        if(index > -1){
          this.answerSelect.splice(index,1)
        }else{
          this.answerSelect.push(item)
        }
      }
    },
    submitFun(){
      feedbackSubmit({
        id:this.row.id,
        questionFeedback:this.questionSelect.toString(),
        answerFeedback:this.answerSelect.toString(),
        opinionFeedback:this.message
      }).then(res=>{
        this.$message.success('提交成功')
        setTimeout(() => {
          this.$emit('close')
        }, 300);
      }) 
    }
  },
};
</script>

<style lang="less" scoped>
.wrapper{
  margin:5px 15px ;
  .tishi{
    font-size: 13px;
    color: #292D32;
    padding: 0 10px;
  }
}
.font-13{
  font-size: 13px;
}
.noactice{
  padding: 4px 8px;
  background: #F8FAFC;
  border-radius:  4px;
  color: #94A3B8;
}
.active{
  padding: 4px 8px;
  color: #2563EB;
  background: #EFF6FF;
  border-radius:  4px;
}
.custom-field .van-field__control::placeholder {
  color: #ff0000; /* 红色文字 */
}

.custom-field .van-field__control {
  background-color: #f0f0f0; /* 浅灰色背景 */
}
.btn{
   position: fixed;
   bottom: 50px;
   padding-bottom: env(safe-area-inset-bottom);
   left: 5px;
   right: 5px;
   .submit{
    background: #EFF6FF;
    border-radius: 20px;
    color: #2563EB;
    text-align: center;
    height: 40px;
    line-height: 40px;
    font-weight: 600;
   }
}
</style>
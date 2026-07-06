<!--
 * @Author: zixin 
 * @Date: 2025-05-22 14:08:32
 * @LastEditors: zixin 
 * @LastEditTime: 2025-06-26 10:30:00
 * @FilePath: \cockpit-mobile-frontend\src\views\ai\module\feedView.vue
 * @Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
-->
<template>
  <div>
    <div>
      <TopTimeSelect class="pl-5 ml-2" v-model="query.startTime" type="date" @change="searchData"
        :disabled="disabledDate" :nextbtn="isNextbtn"></TopTimeSelect>

    </div>
    <div class="mx-3 mt-2">
      <div class="font-13 mb-1 ml-1">
        建议共 <span style="color: #185EFC;">{{ tableData.length }}</span> 条
      </div>
      <Table :fields="tableFields" :tableData="tableData" :maxHeight="520">
        <template slot="id" slot-scope="scope">
          <span>{{ scope.row.indexVal }}</span>
        </template>
        <template slot="detail" slot-scope="{row}">
          <span class="link" @click="handleClick(row)">查看详情</span>
        </template>
      </Table>
    </div>

    <van-popup v-model="showPopup" position="bottom" :style="{ height: '100%' }">
      <div class="flex justify-between align-center mr-5 ml-3">
        <img src="@/assets/images/push/feed.png" alt="" class="">
        <div class="tishi"></div>
        <img src="@/assets/images/push/close.png" alt="" class="" @click="showPopup = false">
      </div>
      <div class="flex ml-3 mr-2 mt-5">
        <img :src="require('@/assets/images/wel/wen.svg')" alt="" class="mr-3"><span>{{ textList.wen }}</span>
      </div>
      <div style="border-bottom: 1px solid #E5E5E5;" class="mt-4 ml-2 mr-2"></div>
      <div class="flex ml-3 mr-2 mt-5">
        <div>
          <img :src="require('@/assets/images/wel/da.svg')" alt="" class="mr-3">

        </div>
        <div>
          <span>
            <Markdown :content="textList.da" />
          </span>
        </div>

      </div>
    </van-popup>
  </div>
</template>
<script>
import dayjs from "dayjs";
import TopTimeSelect from "@/components/tool/TopTimeSelect";
import Table from "@/views/push/components/table.vue";
import Markdown from "./Markdown.vue";
import { histroyList } from "@/api/ai/ai.js";
import {
  gethistory
} from "@/api/ai/ai.js";
export default {
  name: 'feedView',
  data() {
    return {
      disabledDate: dayjs().add(0, 'day').format("YYYY-MM-DD"),
      query: {
        startTime: dayjs().add(0, 'day').format("YYYY-MM-DD"),
      },
      showPopup: false,
      tableFields: [
        {
          prop: "id",
          label: "序号",
          align: "center",
          width: 50,
          slot: 'id'
        },
        {
          prop: "userName",
          label: '用户名',
          align: "center",
          width: 80,
        },
        {
          prop: "questionFeedback",
          label: "针对问题",
          align: "center",
          width: 180,
        },
        {
          prop: "answerFeedback",
          label: "针对回答",
          align: "center",
          width: 180,
        },
        {
          prop: "opinionFeedback",
          label: "补充建议",
          align: "center",
          width: 180,
        },
        {
          prop: "answer",
          label: "Q&A",
          align: "center",
          slot: 'detail',
          fixed: "right",
        },
      ],
      tableData: [],
      textList: {
        wen: '',
        da: ""
      }
    }
  },
  watch: {
    query: {
      handler() {
        this.getTableData();
      },
      deep: true,
    },
  },
  computed: {
    isNextbtn() {
      let b = true
      if (this.query.startTime == this.disabledDate) {
        b = false
      }
      return b
    },
  },
  components: { TopTimeSelect, Table, Markdown },
  methods: {
    searchData() {

    },
    handleClick(item) {
      let str = ''
      let text = ''
      let isJSON = this.isJSON(item.answer)
      if (isJSON) {
        str = JSON.parse(item.answer)
        str.forEach((list) => {
          if (list.type == 'message') {
            text += list.message
          }

        })
      } else {
        text = item.answer
      }



      this.textList.wen = item.question
      this.textList.da = text || ''
      this.showPopup = true

    },
    isJSON(str) {
      try {
        JSON.parse(str);
        return true;
      } catch (e) {
        return false;
      }
    },
    getTableData() {
      histroyList({ userId: '15205009333', times: dayjs(this.query.startTime).format('YYYY-MM') }).then(res => {
        res.data.forEach((item, index) => {
          item.indexVal = index + 1
        })
        this.tableData = res.data
      })
    }
  },
  mounted() {
    this.getTableData()
  },
  created() { },
  beforeDestroy() { }
}
</script>
<style lang="less" scoped>
.font-13 {
  font-size: 13px;
}

.link {
  font-size: 13px;
  color: #185EFC;
  border-bottom: 1px solid #185EFC;
}

/deep/ .select-left--center {
  flex: none;
}

/deep/ .el-table::before {
  width: 100%;
  height: 1px;
}

/deep/ .el-table {
  border-radius: 0px;
}
</style>